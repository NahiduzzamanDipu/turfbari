from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("demo", "0004_interactive_demo")]

    operations = [
        migrations.AddField(
            model_name="demobooking",
            name="slot_count",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="demobooking",
            name="hold_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="demobooking",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
    ]
