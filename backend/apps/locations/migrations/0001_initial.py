import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Division",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=60, unique=True)),
                ("slug", models.SlugField(max_length=60, unique=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="District",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=60, unique=True)),
                ("slug", models.SlugField(max_length=60, unique=True)),
                ("division", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="districts", to="locations.division")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Area",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("district", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="areas", to="locations.district")),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AddConstraint(
            model_name="area",
            constraint=models.UniqueConstraint(fields=("district", "name"), name="uniq_area_per_district"),
        ),
    ]
