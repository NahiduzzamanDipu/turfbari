"""Default plans, and a paid monthly period for every turf that existed before subscriptions."""

from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import migrations

PLANS = [
    ("monthly", "Monthly", 1, Decimal("1500.00"), "Pay month by month."),
    ("half_yearly", "Half-yearly", 6, Decimal("8100.00"), "6 months, save 10%."),
    ("yearly", "Yearly", 12, Decimal("15000.00"), "12 months, save 17%."),
]


def seed(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    for period, name, months, price, description in PLANS:
        Plan.objects.get_or_create(
            period=period, defaults={"name": name, "months": months, "price": price, "description": description}
        )


def backfill(apps, schema_editor):
    import secrets

    Plan = apps.get_model("subscriptions", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Invoice = apps.get_model("subscriptions", "Invoice")
    Turf = apps.get_model("turfs", "Turf")
    monthly = Plan.objects.get(period="monthly")
    today = date.today()
    for turf in Turf.objects.exclude(subscriptions__isnull=False):
        sub = Subscription.objects.create(
            turf=turf,
            plan=monthly,
            status="active",
            starts_on=today,
            ends_on=today + relativedelta(months=1) - timedelta(days=1),
            price=monthly.price,
            note="Starting period when subscriptions were introduced",
        )
        Invoice.objects.create(
            number=f"INV-{today:%y%m}-" + secrets.token_hex(3).upper(),
            turf=turf,
            subscription=sub,
            amount=monthly.price,
            status="paid",
        )


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial"), ("turfs", "0003_turf_coordinates")]

    operations = [
        migrations.RunPython(seed, migrations.RunPython.noop),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
