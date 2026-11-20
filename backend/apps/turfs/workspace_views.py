"""Workspace configuration: fields, hours, pricing, turf settings, managers."""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import credentials
from apps.accounts.models import TemporaryCredential
from apps.accounts.passwords import create_user_with_temporary_password
from apps.audit.services import Category, record
from apps.common.tenancy import IsTenantMember, TenantViewSet

from .images import process_gallery_photo, process_profile_picture
from .models import MANAGER_PERMISSIONS, OperatingHours, PricingRule, TenantMembership, TurfField, TurfPhoto
from .pricing import recompute_min_price
from .serializers import (
    FieldSerializer,
    HoursSerializer,
    MediaURLField,
    PricingRuleSerializer,
    TurfSettingsSerializer,
)


class FieldViewSet(TenantViewSet):
    queryset = TurfField.objects.all()
    serializer_class = FieldSerializer
    owner_only_writes = True
    manager_permission = "manage_slots"
    filter_backends = []
    pagination_class = None
    audit_noun = "field"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        recompute_min_price(self.request.tenant)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        recompute_min_price(self.request.tenant)

    def perform_destroy(self, instance):
        if instance.bookings.exists():
            raise ValidationError(
                {"field": ["This field has bookings, so it can't be deleted. Mark it inactive instead."]}
            )
        super().perform_destroy(instance)
        recompute_min_price(self.request.tenant)


class PricingRuleViewSet(TenantViewSet):
    queryset = PricingRule.objects.select_related("field")
    serializer_class = PricingRuleSerializer
    owner_only_writes = True
    manager_permission = "manage_slots"
    filter_backends = []
    pagination_class = None
    audit_noun = "price rule"

    def perform_create(self, serializer):
        super().perform_create(serializer)
        recompute_min_price(self.request.tenant)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        recompute_min_price(self.request.tenant)

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        recompute_min_price(self.request.tenant)


class HoursView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True
    manager_permission = "manage_slots"

    @extend_schema(tags=["workspace"], responses=HoursSerializer(many=True))
    def get(self, request):
        return Response(HoursSerializer(OperatingHours.objects.filter(turf=request.tenant), many=True).data)

    @extend_schema(
        tags=["workspace"], request=HoursSerializer(many=True), responses=HoursSerializer(many=True)
    )
    @transaction.atomic
    def put(self, request):
        data = HoursSerializer(data=request.data, many=True)
        data.is_valid(raise_exception=True)
        days = [row["weekday"] for row in data.validated_data]
        if sorted(days) != list(range(7)):
            raise ValidationError({"non_field_errors": ["Send exactly one row for each weekday 0–6."]})
        for row in data.validated_data:
            if not row["is_closed"] and row["opens_at"] == row["closes_at"]:
                raise ValidationError({"non_field_errors": ["Opening and closing time can't be the same."]})
            OperatingHours.objects.update_or_create(
                turf=request.tenant,
                weekday=row["weekday"],
                defaults={k: row[k] for k in ("opens_at", "closes_at", "is_closed")},
            )
        closed = [row["weekday"] for row in data.validated_data if row["is_closed"]]
        record(
            "hours.updated",
            "Updated opening hours" + (f" ({len(closed)} closed day(s))" if closed else ""),
            category=Category.SETUP,
            request=request,
        )
        return self.get(request)


def _differs(current, new) -> bool:
    if hasattr(current, "all"):  # many-to-many manager
        return {getattr(x, "pk", x) for x in current.all()} != {getattr(x, "pk", x) for x in new}
    return current != new


class SettingsView(APIView):
    permission_classes = [IsTenantMember]
    owner_only_writes = True

    @extend_schema(tags=["workspace"], responses=TurfSettingsSerializer)
    def get(self, request):
        return Response(TurfSettingsSerializer(request.tenant).data)

    @extend_schema(tags=["workspace"], request=TurfSettingsSerializer, responses=TurfSettingsSerializer)
    def patch(self, request):
        data = TurfSettingsSerializer(request.tenant, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        turf = request.tenant
        changed = sorted(k for k, v in data.validated_data.items() if _differs(getattr(turf, k, None), v))
        data.save()
        if changed:
            record(
                "settings.updated",
                "Updated turf settings: " + ", ".join(f.replace("_", " ") for f in changed)[:200],
                category=Category.SETTINGS,
                request=request,
                data={"fields": changed},
            )
        return Response(data.data)


class BookingQRView(APIView):
    """The turf's own booking-page QR code, for owners and managers (works before the page is published)."""

    permission_classes = [IsTenantMember]

    @extend_schema(tags=["workspace"], responses={200: bytes})
    def get(self, request, kind):
        from django.http import Http404

        from .public_views import qr_response

        if kind not in ("svg", "png"):
            raise Http404
        return qr_response(request.tenant, kind, download=request.query_params.get("download") == "1")


class ManagerSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    role = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)


def manager_row(m: TenantMembership) -> dict:
    return {
        "id": str(m.id),
        "email": m.user.email,
        "full_name": m.user.full_name,
        "phone": m.user.phone,
        "role": m.role,
        "is_active": m.is_active,
        "permissions": {key: m.can(key) for key in MANAGER_PERMISSIONS},
        "must_change_password": m.user.must_change_password,
    }


class ManagerPermissionsSerializer(serializers.Serializer):
    permissions = serializers.DictField(child=serializers.BooleanField())

    def validate_permissions(self, value):
        unknown = set(value) - set(MANAGER_PERMISSIONS)
        if unknown:
            raise ValidationError(f"Unknown permission: {', '.join(sorted(unknown))}")
        return value


class ManagersView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], responses=ManagerSerializer(many=True))
    def get(self, request):
        rows = TenantMembership.objects.filter(turf=request.tenant, is_active=True).select_related("user")
        return Response([manager_row(m) for m in rows.order_by("role", "user__full_name")])

    @extend_schema(tags=["workspace"], request=ManagerSerializer)
    @transaction.atomic
    def post(self, request):
        data = ManagerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        User = get_user_model()
        email = v["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        password = None
        if user is None:
            credentials.require_phone(v.get("phone", ""))
            user, password = create_user_with_temporary_password(
                email, full_name=v["full_name"], phone=v.get("phone", "")
            )
        elif user.is_platform_admin:
            raise ValidationError({"email": ["This email can't be added as a manager."]})
        membership, created = TenantMembership.objects.get_or_create(
            user=user, turf=request.tenant, defaults={"role": TenantMembership.Role.MANAGER}
        )
        if not created:
            if membership.is_active:
                raise ValidationError({"email": ["This person already has access to your turf."]})
            membership.is_active = True
            membership.role = TenantMembership.Role.MANAGER
            membership.save(update_fields=["is_active", "role", "updated_at"])
        record(
            "team.manager_added",
            f"Gave manager access to {user.full_name or user.email} ({user.email})",
            category=Category.TEAM,
            request=request,
            target=membership,
        )
        delivery = {"temporary_password": None, "credential": None}
        if password:  # new account: password goes by SMS (shown once only if SMS is unavailable)
            delivery = credentials.start_delivery(
                user,
                password,
                purpose=TemporaryCredential.Purpose.ACCOUNT_CREATED,
                by=request.user,
                request=request,
            )
        return Response({**manager_row(membership), **delivery}, status=201)


class ManagerDetailView(APIView):
    permission_classes = [IsTenantMember]
    owner_only = True

    @extend_schema(tags=["workspace"], request=ManagerPermissionsSerializer)
    def patch(self, request, pk):
        membership = get_object_or_404(
            TenantMembership.objects.select_related("user"),
            turf=request.tenant,
            pk=pk,
            is_active=True,
            role=TenantMembership.Role.MANAGER,
        )
        data = ManagerPermissionsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership.permissions = {**(membership.permissions or {}), **data.validated_data["permissions"]}
        membership.save(update_fields=["permissions", "updated_at"])
        allowed = [MANAGER_PERMISSIONS[k].lower() for k in MANAGER_PERMISSIONS if membership.can(k)]
        record(
            "team.manager_permissions",
            f"Changed access for {membership.user.full_name or membership.user.email}: "
            + (", ".join(allowed) if allowed else "daily operations only"),
            category=Category.TEAM,
            request=request,
            target=membership,
        )
        return Response(manager_row(membership))

    @extend_schema(tags=["workspace"], responses={204: None})
    def delete(self, request, pk):
        membership = TenantMembership.objects.filter(turf=request.tenant, pk=pk, is_active=True).first()
        if membership is None:
            return Response(
                {"error": {"code": "not_found", "message": "Not found.", "fields": None}}, status=404
            )
        if membership.role == TenantMembership.Role.OWNER:
            raise ValidationError({"role": ["The owner can't be removed."]})
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        record(
            "team.manager_removed",
            f"Removed manager access for {membership.user.full_name or membership.user.email}",
            category=Category.TEAM,
            request=request,
            target=membership,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ pictures
def _delete_files(*files):
    for f in files:
        if f:
            f.delete(save=False)


class PhotoSerializer(serializers.ModelSerializer):
    url = MediaURLField(source="image")
    thumbnail_url = MediaURLField(source="thumbnail")

    class Meta:
        model = TurfPhoto
        fields = ["id", "url", "thumbnail_url", "width", "height", "caption", "sort_order", "created_at"]
        read_only_fields = ["id", "url", "thumbnail_url", "width", "height", "sort_order", "created_at"]


class ProfilePictureView(APIView):
    """One square profile picture per turf (shown on cards and the turf page)."""

    permission_classes = [IsTenantMember]
    owner_only_writes = True
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(tags=["workspace"])
    def post(self, request):
        upload = request.FILES.get("image")
        if not upload:
            raise ValidationError({"image": ["Choose a picture to upload."]})
        processed = process_profile_picture(upload)
        turf = request.tenant
        old = turf.profile_image.name
        turf.profile_image.save(processed.name, processed, save=False)
        turf.save(update_fields=["profile_image", "updated_at"])
        if old:
            turf.profile_image.storage.delete(old)
        record(
            "picture.profile_changed",
            "Changed the profile picture" if old else "Added a profile picture",
            category=Category.SETTINGS,
            request=request,
        )
        return Response({"profile_image_url": turf.profile_image.url})

    @extend_schema(tags=["workspace"])
    def delete(self, request):
        turf = request.tenant
        if turf.profile_image:
            turf.profile_image.delete(save=False)
            turf.profile_image = ""
            turf.save(update_fields=["profile_image", "updated_at"])
            record(
                "picture.profile_removed",
                "Removed the profile picture",
                category=Category.SETTINGS,
                request=request,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PhotoViewSet(TenantViewSet):
    """Public page gallery. Owners manage it; managers can look."""

    queryset = TurfPhoto.objects.all()
    serializer_class = PhotoSerializer
    owner_only_writes = True
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None
    filter_backends = []
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    audit_noun = "photo caption"
    audit_category = Category.SETTINGS

    def create(self, request, *args, **kwargs):
        turf = request.tenant
        uploads = request.FILES.getlist("image")
        if not uploads:
            raise ValidationError({"image": ["Choose at least one picture."]})
        with transaction.atomic():
            # Lock the turf row so two parallel uploads can't both pass the limit check.
            type(turf).objects.select_for_update().get(pk=turf.pk)
            existing = TurfPhoto.objects.filter(turf=turf).count()
            room = TurfPhoto.MAX_PER_TURF - existing
            if len(uploads) > room:
                raise ValidationError(
                    {
                        "image": [
                            f"You can have up to {TurfPhoto.MAX_PER_TURF} photos. Room left: {max(room, 0)}."
                        ]
                    }
                )
            caption = str(request.data.get("caption", ""))[:140]
            processed = [process_gallery_photo(u) for u in uploads]  # validate all before saving any
            created = []
            for offset, (large, thumb, width, height) in enumerate(processed):
                photo = TurfPhoto(
                    turf=turf, caption=caption, sort_order=existing + offset, width=width, height=height
                )
                photo.image.save(large.name, large, save=False)
                photo.thumbnail.save(thumb.name, thumb, save=False)
                photo.save()
                created.append(photo)
        record(
            "picture.photos_added",
            f"Added {len(created)} photo(s) to the public page",
            category=Category.SETTINGS,
            request=request,
        )
        return Response(PhotoSerializer(created, many=True, context={"request": request}).data, status=201)

    def perform_destroy(self, instance):
        _delete_files(instance.image, instance.thumbnail)
        instance.delete()
        record(
            "picture.photo_deleted",
            "Deleted a public page photo" + (f" “{instance.caption}”" if instance.caption else ""),
            category=Category.SETTINGS,
            request=self.request,
        )
        for index, photo in enumerate(TurfPhoto.objects.filter(turf=self.request.tenant)):
            if photo.sort_order != index:
                TurfPhoto.objects.filter(pk=photo.pk).update(sort_order=index)

    @extend_schema(request=serializers.ListSerializer(child=serializers.UUIDField()))
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        ids = [str(i) for i in request.data.get("ids", [])]
        photos = {str(p.id): p for p in TurfPhoto.objects.filter(turf=request.tenant)}
        if sorted(ids) != sorted(photos):
            raise ValidationError({"ids": ["Send every photo id exactly once."]})
        for index, photo_id in enumerate(ids):
            TurfPhoto.objects.filter(pk=photo_id).update(sort_order=index)
        record(
            "picture.reordered", "Reordered public page photos", category=Category.SETTINGS, request=request
        )
        return Response(self.get_serializer(TurfPhoto.objects.filter(turf=request.tenant), many=True).data)
