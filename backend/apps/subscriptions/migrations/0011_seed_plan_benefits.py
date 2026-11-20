from django.db import migrations


FEATURES = [
    "Booking calendar, availability and daily booking management",
    "Custom slot schedules and Morning, Evening, Night and Midnight pricing",
    "Dedicated public booking page and downloadable QR code",
    "Manual bKash payment submission and verification workflow",
    "Customer records and booking history",
    "Owner-controlled staff and manager access",
    "Booking, revenue and business activity reports",
    "Advance and recurring booking series",
]


def seed_features(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    for plan in Plan.objects.all():
        changed = False
        if not plan.features:
            plan.features = FEATURES
            changed = True
        if changed:
            plan.save(update_fields=["features"])
    for subscription in Subscription.objects.all().iterator():
        snapshot = subscription.plan_snapshot or {}
        if not snapshot.get("features"):
            snapshot["features"] = FEATURES
            subscription.plan_snapshot = snapshot
            subscription.save(update_fields=["plan_snapshot"])


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0010_plan_sms_enabled")]
    operations = [migrations.RunPython(seed_features, migrations.RunPython.noop)]
