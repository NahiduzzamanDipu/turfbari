from django.db import migrations, models
import django.db.models.deletion


def merge_demo_workspaces(apps, schema_editor):
    Workspace = apps.get_model("demo", "DemoWorkspace")
    Slot = apps.get_model("demo", "DemoSlot")
    Customer = apps.get_model("demo", "DemoCustomer")
    Booking = apps.get_model("demo", "DemoBooking")
    Activity = apps.get_model("demo", "DemoActivity")
    alias = schema_editor.connection.alias
    workspaces = Workspace.objects.using(alias).order_by("created_at", "id")
    canonical = workspaces.first()
    if canonical is None:
        return

    # The former owner dashboard was private; its contact records now become public.
    # Retain only a masked BD number before merging the old workspaces.
    for customer in Customer.objects.using(alias).all().iterator():
        digits = "".join(ch for ch in customer.phone if ch.isdigit())
        suffix = digits[-4:] if digits else "0000"
        prefix = "+8801" if digits.startswith(("8801", "01", "1")) else ""
        customer.phone = f"{prefix}*****{suffix}"
        customer.save(using=alias, update_fields=["phone"])

    for extra in workspaces.exclude(pk=canonical.pk).iterator():
        for model in (Slot, Customer, Booking, Activity):
            model.objects.using(alias).filter(workspace_id=extra.pk).update(workspace_id=canonical.pk)
        extra.delete(using=alias)

    canonical.name = "TURFBARI Demo Arena"
    canonical.owner_name = "Demo Turf Owner"
    canonical.status = "active"
    canonical.public_key = "public"
    canonical.last_access_at = None
    canonical.save(
        using=alias, update_fields=["name", "owner_name", "status", "public_key", "last_access_at"]
    )


class Migration(migrations.Migration):
    dependencies = [("demo", "0002_remove_demobooking_demo_booking_slot_date_unique")]

    operations = [
        migrations.RemoveConstraint(model_name="democustomer", name="demo_customer_phone_unique"),
        migrations.RemoveIndex(model_name="demoworkspace", name="demo_demowo_status_433e31_idx"),
        migrations.AddField(
            model_name="demoworkspace",
            name="public_key",
            field=models.CharField(blank=True, max_length=20, null=True, unique=True),
        ),
        migrations.RunPython(merge_demo_workspaces, migrations.RunPython.noop),
        migrations.RemoveField(model_name="demoworkspace", name="access_token_hash"),
        migrations.RemoveField(model_name="demoworkspace", name="expires_at"),
        migrations.AlterField(
            model_name="demoworkspace",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("disabled", "Disabled")],
                db_index=True,
                default="active",
                max_length=12,
            ),
        ),
        migrations.AddIndex(
            model_name="demoworkspace",
            index=models.Index(fields=["status", "public_key"], name="demo_demowo_status_public_idx"),
        ),
    ]
