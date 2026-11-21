"""Add a comprehensive bilingual Terms draft without changing published or existing drafts."""

from django.db import migrations

SUMMARY = "Comprehensive bilingual TurfBari Terms draft — legal review required"


def add_terms_draft(apps, schema_editor):
    from apps.legal import content
    from apps.legal.terms_content import terms_text

    Document = apps.get_model("legal", "LegalDocument")
    Version = apps.get_model("legal", "LegalDocumentVersion")
    doc = Document.objects.filter(category="terms", sector__isnull=True, is_archived=False).first()
    if doc is None or Version.objects.filter(document=doc, change_summary=SUMMARY).exists():
        return

    text = terms_text()
    latest = Version.objects.filter(document=doc).order_by("-version").first()
    Version.objects.create(
        document=doc,
        version=(latest.version + 1) if latest else 1,
        status="draft",
        title_en=text["title_en"],
        title_bn=text["title_bn"],
        body_en=content.sanitize(text["body_en"]),
        body_bn=content.sanitize(text["body_bn"]),
        change_summary=SUMMARY,
        reacceptance="all",
    )


class Migration(migrations.Migration):
    dependencies = [("legal", "0003_standard_drafts")]
    operations = [migrations.RunPython(add_terms_draft, migrations.RunPython.noop)]
