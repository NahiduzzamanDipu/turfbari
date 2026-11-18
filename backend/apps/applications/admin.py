from django.contrib import admin

from .models import TurfApplication


@admin.register(TurfApplication)
class TurfApplicationAdmin(admin.ModelAdmin):
    list_display = ["turf_name", "owner_name", "phone", "status", "created_at"]
    list_filter = ["status"]
