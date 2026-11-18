from django.contrib import admin

from .models import Booking, Customer, MaintenanceBlock, Payment


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ["reference", "turf", "field", "start", "status", "total", "amount_paid"]
    list_filter = ["status", "source"]
    search_fields = ["reference", "customer__name", "customer__phone"]


admin.site.register([Customer, Payment, MaintenanceBlock])
