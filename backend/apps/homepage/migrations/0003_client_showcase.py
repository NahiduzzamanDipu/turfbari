import uuid

import django.db.models.deletion
from django.db import migrations, models


def create_default_settings(apps, schema_editor):
    Settings = apps.get_model("homepage", "ClientShowcaseSettings")
    Settings.objects.get_or_create(
        key="homepage",
        defaults={
            "enabled": True,
            "auto_include": True,
            "heading_en": "Our Trusted Clients",
            "heading_bn": "আমাদের সম্মানিত গ্রাহক",
            "subtitle_en": "Turf businesses growing with TURFBARI.",
            "subtitle_bn": "যেসব টার্ফ ব্যবসা TURFBARI-এর সঙ্গে এগিয়ে যাচ্ছে।",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("homepage", "0002_seed_homepage_faqs"),
        ("subscriptions", "0011_seed_plan_benefits"),
        ("turfs", "0012_turf_sector"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientShowcaseSettings",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("key", models.CharField(default="homepage", max_length=32, unique=True)),
                ("enabled", models.BooleanField(default=True)),
                ("auto_include", models.BooleanField(default=True)),
                ("heading_en", models.CharField(default="Our Trusted Clients", max_length=120)),
                ("heading_bn", models.CharField(default="আমাদের সম্মানিত গ্রাহক", max_length=120)),
                (
                    "subtitle_en",
                    models.CharField(default="Turf businesses growing with TURFBARI.", max_length=200),
                ),
                (
                    "subtitle_bn",
                    models.CharField(default="যেসব টার্ফ ব্যবসা TURFBARI-এর সঙ্গে এগিয়ে যাচ্ছে।", max_length=200),
                ),
                (
                    "eligible_plans",
                    models.ManyToManyField(
                        blank=True, related_name="showcase_settings", to="subscriptions.plan"
                    ),
                ),
            ],
            options={"verbose_name": "homepage client showcase settings"},
        ),
        migrations.CreateModel(
            name="ClientShowcaseOverride",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                (
                    "mode",
                    models.CharField(
                        choices=[("auto", "Automatic"), ("include", "Include"), ("hide", "Hide")],
                        default="auto",
                        max_length=8,
                    ),
                ),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "turf",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="showcase_override",
                        to="turfs.turf",
                    ),
                ),
            ],
            options={"ordering": ["display_order", "turf__name"]},
        ),
        migrations.RunPython(create_default_settings, migrations.RunPython.noop),
    ]
