from django.contrib import admin

from .models import Amenity, OperatingHours, PricingRule, TenantMembership, Turf, TurfField


class FieldInline(admin.TabularInline):
    model = TurfField
    extra = 0


class MembershipInline(admin.TabularInline):
    model = TenantMembership
    extra = 0
    raw_id_fields = ["user"]


@admin.register(Turf)
class TurfAdmin(admin.ModelAdmin):
    list_display = ["name", "district", "status", "is_listed", "is_featured"]
    list_filter = ["status", "is_listed", "turf_type"]
    search_fields = ["name", "address"]
    inlines = [FieldInline, MembershipInline]


admin.site.register([Amenity, OperatingHours, PricingRule])
