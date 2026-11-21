"""Customer list XLSX export: aggregation, safety, permissions and tenant isolation."""

from datetime import timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from openpyxl import load_workbook

from apps.audit.models import AuditEvent
from apps.bookings.models import Booking, Customer
from apps.bookings.services import get_or_create_customer
from apps.turfs.models import TenantMembership

from .test_core import PASSWORD, client_for, make_turf, tomorrow_at

pytestmark = pytest.mark.django_db


def create_booking(turf, customer, *, status, hour, hold_expires_at=None):
    start = tomorrow_at(hour)
    return Booking.objects.create(
        turf=turf,
        customer=customer,
        field=turf.fields.first(),
        start=start,
        end=start + timedelta(hours=1),
        status=status,
        subtotal=Decimal("1000.00"),
        discount=Decimal("0.00"),
        total=Decimal("1000.00"),
        amount_paid=Decimal("0.00"),
        hold_expires_at=hold_expires_at,
    )


def workbook_from(response):
    assert response.status_code == 200
    payload = b"".join(response.streaming_content)
    return load_workbook(BytesIO(payload), data_only=False)


def test_owner_exports_unique_customers_with_aggregates_and_safe_xlsx_text():
    turf, owner = make_turf()
    customer = get_or_create_customer(
        turf,
        name='=HYPERLINK("https://bad.example","Click")',
        phone="+8801712345678",
        email="customer@example.com",
    )
    customer.notes = "@SUM(1,1)"
    customer.save(update_fields=["notes"])
    now = timezone.now()
    for status, hour, hold in [
        (Booking.Status.CONFIRMED, 8, None),
        (Booking.Status.COMPLETED, 9, None),
        (Booking.Status.PENDING, 10, now + timedelta(hours=1)),
        (Booking.Status.PENDING, 11, now - timedelta(hours=1)),
        (Booking.Status.CANCELLED, 12, None),
        (Booking.Status.REJECTED, 13, None),
    ]:
        create_booking(turf, customer, status=status, hour=hour, hold_expires_at=hold)
    get_or_create_customer(turf, name="No bookings yet", phone="01812345678")
    other_turf, _ = make_turf("Other Turf", "other@example.com")
    get_or_create_customer(other_turf, name="Other tenant", phone="01912345678")

    response = client_for(owner).get(f"/api/workspace/customers/export.xlsx?turf={other_turf.pk}&lang=en")
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Exported-Count"] == "2"
    assert "attachment" in response["Content-Disposition"]
    wb = workbook_from(response)
    ws = wb["Customers"]
    assert ws.freeze_panes == "A7"
    assert ws.auto_filter.ref == "A6:M8"
    assert ws.cell(6, 1).value == "Customer ID"
    row = next(r for r in ws.iter_rows(min_row=7, values_only=True) if r[1] == customer.name)
    assert row[0] == str(customer.pk)
    assert row[2] == "+8801712345678"
    assert (row[4], row[5], row[6], row[7], row[8]) == (6, 2, 1, 1, 1)
    assert row[9] == 6000
    assert row[12] == customer.notes
    assert ws["B7"].data_type == "s"  # formula-looking customer text is an XLSX string cell
    assert ws["M7"].data_type == "s"
    assert AuditEvent.objects.filter(
        action="customer.exported", turf=turf, data__export_type="all", data__record_count=2
    ).exists()


def test_filtered_export_ignores_current_page_and_only_matches_current_tenant():
    turf, owner = make_turf()
    target = get_or_create_customer(turf, name="Rafi Ahmed", phone="01712345678")
    create_booking(turf, target, status=Booking.Status.CONFIRMED, hour=10)
    get_or_create_customer(turf, name="Sadia Rahman", phone="01812345678")
    other_turf, _ = make_turf("Beta Turf", "beta@example.com")
    get_or_create_customer(other_turf, name="Rafi from Beta", phone="01912345678")

    response = client_for(owner).get("/api/workspace/customers/export.xlsx?q=Rafi&lang=bn")
    assert response["X-Exported-Count"] == "1"
    ws = workbook_from(response)["Customers"]
    assert ws["A6"].value == "গ্রাহক আইডি"
    assert ws["B7"].value == "Rafi Ahmed"
    assert ws.max_row == 7
    assert AuditEvent.objects.filter(
        action="customer.exported", turf=turf, data__export_type="filtered", data__search_applied=True
    ).exists()


def test_export_contains_customers_beyond_the_visible_list_page_and_empty_search_is_a_clear_404():
    turf, owner = make_turf()
    Customer.objects.bulk_create(
        [
            Customer(turf=turf, name=f"Customer {index:03}", phone=f"+88017{index:08}")
            for index in range(25)
        ]
    )
    client = client_for(owner)
    response = client.get("/api/workspace/customers/export.xlsx")
    assert response["X-Exported-Count"] == "25"
    assert workbook_from(response)["Customers"].max_row == 31

    empty = client.get("/api/workspace/customers/export.xlsx?q=does-not-exist")
    assert empty.status_code == 404
    assert AuditEvent.objects.filter(action="customer.export_empty", turf=turf).exists()


def test_manager_needs_explicit_export_permission_and_is_tenant_scoped():
    turf, _ = make_turf()
    customer = get_or_create_customer(turf, name="Owner customer", phone="01712345678")
    User = get_user_model()
    manager = User.objects.create_user("export-manager@example.com", PASSWORD)
    membership = TenantMembership.objects.create(user=manager, turf=turf, role="manager")
    client = client_for(manager)
    assert client.get("/api/workspace/customers/export.xlsx").status_code == 403

    membership.permissions = {**membership.permissions, "export_customers": True}
    membership.save(update_fields=["permissions", "updated_at"])
    other_turf, _ = make_turf("Separate", "separate@example.com")
    get_or_create_customer(other_turf, name="Not visible", phone="01812345678")
    response = client.get(f"/api/workspace/customers/export.xlsx?turf={other_turf.pk}")
    ws = workbook_from(response)["Customers"]
    assert response["X-Exported-Count"] == "1"
    assert ws["B7"].value == customer.name
