from django.db import migrations
from django.utils.text import slugify

AMENITIES = [
    "Floodlights", "Parking", "Washroom", "Changing room", "Drinking water", "Cafeteria",
    "Prayer room", "First aid", "Seating area", "Wi-Fi", "Equipment rental", "CCTV",
]


def seed(apps, schema_editor):
    Amenity = apps.get_model("turfs", "Amenity")
    for name in AMENITIES:
        Amenity.objects.get_or_create(slug=slugify(name), defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("turfs", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
