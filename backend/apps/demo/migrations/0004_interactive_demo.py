import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("demo", "0003_permanent_shared_demo")]

    operations = [
        migrations.AddField(
            model_name="demoworkspace",
            name="last_reset_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="payment_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="sender_phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="transaction_reference",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Awaiting demo verification"),
                    ("approved", "Approved in demo"),
                    ("rejected", "Rejected in demo"),
                ],
                default="pending",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="terms_version_ids",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="terms_agreed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="democustomer",
            name="phone_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="rejection_reason",
            field=models.CharField(blank=True, max_length=300),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="reviewed_by",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="demobooking",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("workspace", "idempotency_key"),
                name="demo_booking_idempotency_unique",
            ),
        ),
        migrations.CreateModel(
            name="DemoHold",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("date", models.DateField()),
                ("visitor_id", models.CharField(max_length=64)),
                ("token", models.UUIDField(db_index=True, default=uuid.uuid4)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("slot", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holds", to="demo.demoslot")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="holds", to="demo.demoworkspace")),
            ],
        ),
        migrations.AddConstraint(
            model_name="demohold",
            constraint=models.UniqueConstraint(fields=("workspace", "date", "slot"), name="demo_hold_slot_day_unique"),
        ),
        migrations.AddIndex(
            model_name="demohold",
            index=models.Index(fields=["workspace", "date", "expires_at"], name="demo_demoho_workspa_59c80a_idx"),
        ),
        migrations.CreateModel(
            name="DemoSms",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("booking_request", "Booking request"), ("booking_approved", "Booking approved"), ("booking_rejected", "Booking rejected"), ("booking_cancelled", "Booking cancelled")], max_length=24)),
                ("recipient", models.CharField(blank=True, max_length=20)),
                ("body", models.CharField(max_length=500)),
                ("status", models.CharField(default="simulated", max_length=20)),
                ("booking", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="sms_messages", to="demo.demobooking")),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sms_messages", to="demo.demoworkspace")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="demoactivity",
            name="actor_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
