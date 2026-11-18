from django.db import migrations
from django.utils.text import slugify


def seed(apps, schema_editor):
    from apps.locations.data import AREAS, DIVISIONS

    Division = apps.get_model("locations", "Division")
    District = apps.get_model("locations", "District")
    Area = apps.get_model("locations", "Area")
    for division_name, districts in DIVISIONS.items():
        division, _ = Division.objects.get_or_create(slug=slugify(division_name), defaults={"name": division_name})
        for district_name in districts:
            district, _ = District.objects.get_or_create(
                slug=slugify(district_name), defaults={"name": district_name, "division": division}
            )
            for area_name in AREAS.get(district_name, []):
                Area.objects.get_or_create(
                    slug=slugify(f"{area_name}-{district_name}"), defaults={"name": area_name, "district": district}
                )


class Migration(migrations.Migration):
    dependencies = [("locations", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
