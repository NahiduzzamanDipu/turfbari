from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("common", "0005_bkash_account_type")]

    operations = [
        migrations.AddField("platformsettings", "contact_enabled", models.BooleanField(default=True)),
        migrations.AddField("platformsettings", "contact_phone", models.CharField(blank=True, max_length=30)),
        migrations.AddField("platformsettings", "contact_email", models.EmailField(blank=True, max_length=254)),
        migrations.AddField("platformsettings", "contact_facebook_url", models.URLField(blank=True, max_length=300)),
        migrations.AddField("platformsettings", "contact_whatsapp", models.CharField(blank=True, max_length=30)),
        migrations.AddField("platformsettings", "contact_address", models.CharField(blank=True, max_length=300)),
        migrations.AddField("platformsettings", "contact_heading", models.CharField(blank=True, max_length=120)),
        migrations.AddField("platformsettings", "contact_description", models.CharField(blank=True, max_length=300)),
        migrations.AddField("platformsettings", "contact_show_phone", models.BooleanField(default=True)),
        migrations.AddField("platformsettings", "contact_show_email", models.BooleanField(default=True)),
        migrations.AddField("platformsettings", "contact_show_facebook", models.BooleanField(default=True)),
        migrations.AddField("platformsettings", "contact_show_whatsapp", models.BooleanField(default=True)),
        migrations.AddField("platformsettings", "contact_show_address", models.BooleanField(default=True)),
    ]
