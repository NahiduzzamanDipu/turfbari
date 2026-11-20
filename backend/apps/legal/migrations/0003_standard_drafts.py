"""Adds TurfBari's standard wording as a DRAFT to every module that doesn't already have a draft.

Nothing is published: an admin reviews (ideally with a lawyer), edits and publishes each one."""

from django.db import migrations

from apps.legal import content
from apps.legal.standard_text import standard_text


def add_drafts(apps, schema_editor):
    Document = apps.get_model("legal", "LegalDocument")
    Version = apps.get_model("legal", "LegalDocumentVersion")
    for doc in Document.objects.filter(is_archived=False).select_related("sector"):
        if Version.objects.filter(document=doc, status="draft").exists():
            continue
        text = standard_text(
            doc.category,
            doc.sector.name_en if doc.sector_id else None,
            doc.sector.name_bn if doc.sector_id else None,
        )
        if text is None:
            continue
        latest = Version.objects.filter(document=doc).order_by("-version").first()
        Version.objects.create(
            document=doc,
            version=(latest.version + 1) if latest else 1,
            status="draft",
            title_en=text["title_en"],
            title_bn=text["title_bn"],
            body_en=content.sanitize(text["body_en"]),
            body_bn=content.sanitize(text["body_bn"]),
            change_summary="TurfBari standard text — review and edit before publishing",
        )


def remove_drafts(apps, schema_editor):
    apps.get_model("legal", "LegalDocumentVersion").objects.filter(
        status="draft", change_summary="TurfBari standard text — review and edit before publishing"
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("legal", "0002_seed_and_migrate_terms")]

    operations = [migrations.RunPython(add_drafts, remove_drafts)]
