from django.db import migrations


def snapshot_existing(apps, schema_editor):
    Subscription = apps.get_model("subscriptions", "Subscription")
    Plan = apps.get_model("subscriptions", "Plan")
    for subscription in Subscription.objects.all().iterator():
        try:
            plan = Plan.objects.get(pk=subscription.plan_id)
        except Plan.DoesNotExist:
            continue
        subscription.plan_snapshot = {
            "name": plan.name,
            "period": plan.period,
            "months": plan.months,
            "price": str(subscription.price),
            "description": plan.description,
            "features": plan.features or [],
            "limits": plan.limits or {},
            "sms_enabled": getattr(plan, "sms_enabled", True),
        }
        subscription.save(update_fields=["plan_snapshot"])


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0008_alter_plan_options_plan_display_order_plan_featured_and_more")]
    operations = [migrations.RunPython(snapshot_existing, migrations.RunPython.noop)]
