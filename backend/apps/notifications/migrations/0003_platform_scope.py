from django.db import migrations

PLATFORM_KINDS = ["subscription_reminder", "subscription_expired", "password_reset", "test"]


def forwards(apps, schema_editor):
    apps.get_model("notifications", "SmsMessage").objects.filter(kind__in=PLATFORM_KINDS).update(scope="platform")


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_smsconfig_api_key_encrypted_smsmessage_provider_ref_and_more")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
