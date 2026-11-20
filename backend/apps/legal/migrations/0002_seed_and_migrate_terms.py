"""Seeds the first sector and the document modules, then moves the old single Terms system into the new
one without losing anything:

- every TermsVersion becomes version N of "Terms & Conditions" (terms text) and of the
  "Booking & Reservation Policy" (the old booking rules text), keeping status and publish dates;
- every booking that agreed to TermsVersion N gets acceptance records for exactly those two versions,
  dated when the customer agreed.

Documents are only created as empty shells: nothing new is published (no placeholder legal text)."""

from django.db import migrations

from apps.legal import catalog, content

SECTOR = ("football-turf", "Football Turf & Sports Facilities", "ফুটবল টার্ফ ও স্পোর্টস ফ্যাসিলিটি")


def _bodies(text: str) -> tuple[str, str]:
    html = content.markdown_lite_to_html(text)
    return ("", html) if content.has_bengali(text) else (html, "")


def seed(apps, schema_editor):
    """The first sector and the empty document modules (idempotent; also used by the test suite)."""
    Sector = apps.get_model("legal", "Sector")
    Document = apps.get_model("legal", "LegalDocument")
    Turf = apps.get_model("turfs", "Turf")
    Application = apps.get_model("applications", "TurfApplication")

    slug, name_en, name_bn = SECTOR
    sector, _ = Sector.objects.get_or_create(slug=slug, defaults={"name_en": name_en, "name_bn": name_bn})
    Turf.objects.filter(sector__isnull=True).update(sector=sector)
    Application.objects.filter(sector__isnull=True).update(sector=sector)

    docs = {}
    for category in catalog.ORDER:
        doc_slug, _, _, audiences, actions = catalog.DEFAULTS[category]
        is_sector = category in catalog.SECTOR_CATEGORIES
        doc, _ = Document.objects.get_or_create(
            category=category,
            sector=sector if is_sector else None,
            defaults={
                "slug": doc_slug,
                "audiences": audiences,
                "actions": actions,
                "sort_order": catalog.sort_key(category),
            },
        )
        docs[category] = doc
    return docs


def forwards(apps, schema_editor):
    Version = apps.get_model("legal", "LegalDocumentVersion")
    Acceptance = apps.get_model("legal", "LegalAcceptance")
    TermsVersion = apps.get_model("common", "TermsVersion")
    Booking = apps.get_model("bookings", "Booking")
    docs = seed(apps, schema_editor)

    mapping = {}  # TermsVersion pk -> [new version ids]
    for old in TermsVersion.objects.order_by("version"):
        new_ids = []
        for category, text in (("terms", old.terms_body), ("booking", old.rules_body)):
            _, title_en, title_bn, _, _ = catalog.DEFAULTS[category]
            body_en, body_bn = _bodies(text)
            v = Version.objects.create(
                document=docs[category],
                version=old.version,
                status=old.status,
                title_en=title_en,
                title_bn=title_bn,
                body_en=body_en,
                body_bn=body_bn,
                change_summary=f"Moved from the previous Terms system (v{old.version})",
                reacceptance="none",
                effective_at=old.published_at,
                published_at=old.published_at,
                published_by_id=old.published_by_id,
            )
            Version.objects.filter(pk=v.pk).update(created_at=old.created_at)
            new_ids.append((v.pk, docs[category]))
        mapping[old.pk] = new_ids

    for booking in Booking.objects.filter(terms_version__isnull=False).select_related("turf").iterator():
        for version_id, doc in mapping.get(booking.terms_version_id, []):
            a = Acceptance.objects.create(
                version_id=version_id,
                document=doc,
                category=doc.category,
                sector_id=booking.turf.sector_id,
                turf_id=booking.turf_id,
                booking=booking,
                action="booking",
                related_ref=f"booking:{booking.reference}",
            )
            when = booking.terms_agreed_at or booking.created_at
            Acceptance.objects.filter(pk=a.pk).update(accepted_at=when)


def backwards(apps, schema_editor):
    for model in ("LegalAcceptance", "LegalDocumentVersion", "LegalDocument"):
        apps.get_model("legal", model).objects.all().delete()
    apps.get_model("turfs", "Turf").objects.update(sector=None)
    apps.get_model("applications", "TurfApplication").objects.update(sector=None)
    apps.get_model("legal", "Sector").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("legal", "0001_initial"),
        ("turfs", "0012_turf_sector"),
        ("applications", "0003_business_sector"),
        ("common", "0002_sms_wallet"),
        ("bookings", "0006_customer_phone_index"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
