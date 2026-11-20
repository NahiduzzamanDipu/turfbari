from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def seed_default_price(apps, schema_editor):
    Pricing = apps.get_model("notifications", "SmsPricing")
    if not Pricing.objects.exists():
        # Initial admin-configurable baseline; future effective-dated rows replace it.
        Pricing.objects.create(
            price_per_segment=Decimal("0.3500"),
            masking_price_per_segment=Decimal("0.3500"),
            bulk_price_per_segment=Decimal("0.3500"),
            effective_from=timezone.now(),
            note="Initial baseline SMS price per segment",
        )


class Migration(migrations.Migration):
    dependencies = [("notifications", "0006_recurring_bookings")]
    operations = [migrations.RunPython(seed_default_price, migrations.RunPython.noop)]
