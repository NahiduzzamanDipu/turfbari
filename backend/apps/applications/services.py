"""Turn an approved application (or an admin form) into a live turf with an owner login."""

import secrets
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.subscriptions.models import Plan
from apps.subscriptions.services import assign_plan
from apps.turfs.models import TenantMembership, Turf
from apps.turfs.services import provision_defaults, unique_slug

from .models import TurfApplication


def temporary_password() -> str:
    return secrets.token_urlsafe(9)  # 12 chars, shown once to the admin


@transaction.atomic
def create_turf_with_owner(
    *,
    name,
    district,
    area,
    address,
    turf_type,
    owner_email,
    owner_name,
    owner_phone,
    number_of_fields=1,
    hourly_rate=Decimal("1500.00"),
    plan=None,
    payment_received=True,
    assigned_by=None,
) -> tuple[Turf, object, str | None]:
    """Returns (turf, owner_user, temp_password or None if the owner already had an account).

    `plan` defaults to the monthly plan. With payment_received=False the first period waits for the
    owner to pay from their workspace (the turf stays off Explore until then)."""
    User = get_user_model()
    owner_email = owner_email.strip().lower()
    owner = User.objects.filter(email=owner_email).first()
    password = None
    if owner is None:
        password = temporary_password()
        owner = User.objects.create_user(owner_email, password, full_name=owner_name, phone=owner_phone)
    elif owner.is_platform_admin:
        raise ValidationError({"email": ["This email belongs to a platform administrator."]})

    turf = Turf.objects.create(
        name=name,
        slug=unique_slug(name),
        district=district,
        area=area,
        address=address,
        turf_type=turf_type,
        owner_name=owner_name,
        owner_phone=owner_phone,
        public_phone=owner_phone,
        weekend_days=[4, 5],
    )
    TenantMembership.objects.create(user=owner, turf=turf, role=TenantMembership.Role.OWNER)
    provision_defaults(turf, fields=number_of_fields, hourly_rate=hourly_rate)
    plan = plan or Plan.objects.get(period=Plan.Period.MONTHLY)
    assign_plan(turf, plan, paid=payment_received, by=assigned_by, note="First subscription")
    return turf, owner, password


@transaction.atomic
def approve_application(
    application: TurfApplication,
    *,
    reviewer,
    hourly_rate=Decimal("1500.00"),
    plan=None,
    payment_received=True,
) -> dict:
    application = TurfApplication.objects.select_for_update().get(pk=application.pk)
    if application.status == TurfApplication.Status.APPROVED:
        raise ValidationError({"status": ["This application is already approved."]})
    if application.status == TurfApplication.Status.REJECTED:
        raise ValidationError({"status": ["Rejected applications cannot be approved. Reopen it first."]})
    turf, owner, password = create_turf_with_owner(
        name=application.turf_name,
        district=application.district,
        area=application.area,
        address=application.address,
        turf_type=application.turf_type,
        owner_email=application.email,
        owner_name=application.owner_name,
        owner_phone=application.phone,
        number_of_fields=application.number_of_fields,
        hourly_rate=hourly_rate,
        plan=plan,
        payment_received=payment_received,
        assigned_by=reviewer,
    )
    application.status = TurfApplication.Status.APPROVED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.turf = turf
    application.save()
    return {"turf": turf, "owner": owner, "temporary_password": password}
