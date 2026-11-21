"""Public, approved TURFBARI knowledge ingestion and retrieval."""

import hashlib
import re

from django.utils import timezone

from apps.common.models import PlatformSettings
from apps.homepage.models import HomepageFAQ
from apps.notifications.models import SmsPricing
from apps.subscriptions.models import Plan

from .models import KnowledgeArticle, KnowledgeChunk, KnowledgeSource


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _clean(value: str) -> str:
    paragraphs = [re.sub(r"\s+", " ", paragraph).strip() for paragraph in (value or "").splitlines()]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def split_chunks(text: str, size: int = 900) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current = [], ""
    for paragraph in paragraphs:
        while len(paragraph) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:size])
            paragraph = paragraph[size:]
        if current and len(current) + len(paragraph) + 1 > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def _replace_source(
    key: str,
    title: str,
    language: str,
    version: str,
    content: str,
    *,
    public_url: str = "",
) -> dict:
    content = _clean(content)
    digest = _hash(f"{title}\n{public_url}\n{content}")
    source, _ = KnowledgeSource.objects.get_or_create(
        key=key, defaults={"title": title, "language": language}
    )
    if (
        source.content_hash == digest
        and source.status == KnowledgeSource.Status.INDEXED
        and source.chunks.exists()
    ):
        return {"key": key, "status": source.status, "changed": False}
    source.title, source.language, source.version = title, language, version
    source.public_url = public_url
    source.source_type = "article" if key.startswith("article:") else "built_in"
    source.content_hash, source.status, source.error_code = digest, KnowledgeSource.Status.PROCESSING, ""
    source.save()
    source.chunks.all().delete()
    try:
        rows = []
        for ordinal, chunk in enumerate(split_chunks(content)):
            rows.append(KnowledgeChunk(source=source, ordinal=ordinal, text=chunk, content_hash=_hash(chunk)))
        KnowledgeChunk.objects.bulk_create(rows)
        source.status = KnowledgeSource.Status.INDEXED
        source.indexed_at = timezone.now()
        source.save(update_fields=["status", "indexed_at", "updated_at"])
        return {"key": key, "status": source.status, "changed": True}
    except Exception:
        source.status, source.error_code = KnowledgeSource.Status.FAILED, "index_failed"
        source.save(update_fields=["status", "error_code", "updated_at"])
        raise


def sync_knowledge() -> dict:
    """Rebuild published public sources and admin-published articles only. Drafts are excluded."""
    results = []
    overview = (
        "TURFBARI is a SaaS platform for football turf businesses in Bangladesh. "
        "Owners can publish their own booking page and QR code, configure fields, opening hours, "
        "custom slots and pricing, manage customer bookings, review manual bKash payments, manage staff, "
        "use SMS wallet services, and view operating reports. Customers can book from a turf's public page. "
        "Registration and subscription payments are reviewed by the platform administrator. "
        "The product has a public demo, turf registration, login, legal policies and contact pages."
    )
    results.append(
        _replace_source(
            "homepage:overview:en",
            "TURFBARI platform overview",
            "en",
            "homepage-v1",
            overview,
            public_url="/",
        )
    )
    overview_bn = (
        "টার্ফবাড়ি বাংলাদেশের ফুটবল টার্ফ ব্যবসার জন্য একটি ব্যবস্থাপনা প্ল্যাটফর্ম। "
        "মালিকেরা নিজস্ব বুকিং পেজ, QR কোড, মাঠ, খোলার সময়, কাস্টম স্লট ও মূল্য পরিচালনা করতে পারেন। "
        "তারা বুকিং, গ্রাহক, কর্মী, bKash পেমেন্ট যাচাই, SMS Wallet এবং রিপোর্টও পরিচালনা করতে পারেন। "
        "গ্রাহকেরা টার্ফের পাবলিক পেজ থেকে স্লট বুক করতে পারেন।"
    )
    results.append(
        _replace_source(
            "homepage:overview:bn",
            "টার্ফবাড়ি প্ল্যাটফর্ম পরিচিতি",
            "bn",
            "homepage-v1",
            overview_bn,
            public_url="/",
        )
    )
    for faq in HomepageFAQ.objects.filter(is_published=True):
        for language, question, answer in (
            ("en", faq.question_en, faq.answer_en),
            ("bn", faq.question_bn, faq.answer_bn),
        ):
            if question and answer:
                results.append(
                    _replace_source(
                        f"faq:{faq.pk}:{language}",
                        question,
                        language,
                        str(faq.updated_at),
                        f"{question}\n\n{answer}",
                        public_url="/#faq-title",
                    )
                )
    for plan in Plan.objects.filter(is_active=True, is_public=True):
        body = "\n".join(
            [
                plan.name,
                plan.description,
                f"Price: BDT {plan.price}",
                f"Period: {plan.months} months",
                f"Features: {', '.join(plan.features or [])}",
                f"Limits: {plan.limits}",
            ]
        )
        results.append(
            _replace_source(
                f"plan:{plan.pk}:en",
                plan.name,
                "en",
                str(plan.updated_at),
                body,
                public_url="/#plans",
            )
        )
    rate = (
        SmsPricing.objects.filter(effective_from__lte=timezone.now())
        .order_by("-effective_from", "-id")
        .first()
    )
    if rate:
        results.append(
            _replace_source(
                "sms-pricing:current",
                "Current SMS pricing",
                "en",
                str(rate.effective_from),
                f"Current SMS price is BDT {rate.price_per_segment} per segment, "
                f"effective {rate.effective_from:%Y-%m-%d}.",
            )
        )
    from apps.legal.services import current_versions_qs

    legal_versions = current_versions_qs().filter(published_at__isnull=False)
    for version in legal_versions:
        for language, title, body in (
            ("en", version.title_en, version.body_en),
            ("bn", version.title_bn, version.body_bn),
        ):
            plain = re.sub(r"<[^>]*>", " ", body or "")
            if title and plain.strip():
                key = f"legal:{version.pk}:{language}"
                results.append(
                    _replace_source(
                        key,
                        title,
                        language,
                        f"v{version.version}",
                        f"{title}\n\n{plain}",
                        public_url=(
                            f"/legal/sector/{version.document.sector.slug}#{version.document.category}"
                            if version.document.sector_id
                            else f"/legal/{version.document.slug}"
                        ),
                    )
                )
    for article in KnowledgeArticle.objects.filter(is_published=True):
        for language, title, body in (
            ("en", article.title_en, article.body_en),
            ("bn", article.title_bn, article.body_bn),
        ):
            if title and body:
                results.append(
                    _replace_source(
                        f"article:{article.pk}:{language}",
                        title,
                        language,
                        str(article.updated_at),
                        f"{title}\n\n{body}",
                    )
                )
    active_keys = {r["key"] for r in results}
    for prefix in ("faq:", "plan:", "legal:", "article:", "sms-pricing:"):
        KnowledgeSource.objects.filter(key__startswith=prefix).exclude(key__in=active_keys).delete()
    return {
        "indexed": sum(1 for item in results if item["status"] == "indexed"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "sources": len(results),
    }


def live_facts(question: str) -> list[str]:
    """Fetch current platform values directly from TURFBARI's database."""
    q = question.casefold()
    snippets = []
    money_terms = (
        "price",
        "cost",
        "plan",
        "subscription",
        "sms",
        "\u09a6\u09be\u09ae",
        "\u0996\u09b0\u099a",
        "\u09b8\u09be\u09ac\u09b8\u09cd\u0995\u09cd\u09b0\u09bf\u09aa\u09b6\u09a8",
        "\u099f\u09be\u0995\u09be",
    )
    if any(word in q for word in money_terms):
        plans = Plan.objects.filter(is_active=True, is_public=True).order_by("display_order", "months")
        snippets.extend(f"{p.name}: BDT {p.price}, {p.months} months. {p.description}" for p in plans)
        sms = (
            SmsPricing.objects.filter(effective_from__lte=timezone.now())
            .order_by("-effective_from", "-id")
            .first()
        )
        if sms and any(word in q for word in ("sms", "segment", "\u098f\u09b8\u098f\u09ae\u098f\u09b8")):
            snippets.append(f"SMS: BDT {sms.price_per_segment} per billable segment.")
    contact_terms = (
        "contact",
        "phone",
        "email",
        "\u09af\u09cb\u0997\u09be\u09af\u09cb\u0997",
        "\u09ab\u09cb\u09a8",
        "\u0987\u09ae\u09c7\u0987\u09b2",
    )
    if any(word in q for word in contact_terms):
        settings = PlatformSettings.load()
        if settings.contact_enabled:
            snippets.extend(
                value
                for value in (
                    f"Support phone: {settings.contact_phone}"
                    if settings.contact_show_phone and settings.contact_phone
                    else "",
                    f"Support email: {settings.contact_email}"
                    if settings.contact_show_email and settings.contact_email
                    else "",
                    f"Facebook: {settings.contact_facebook_url}"
                    if settings.contact_show_facebook and settings.contact_facebook_url
                    else "",
                )
                if value
            )
    return snippets


def retrieve(question: str, limit: int = 4, language: str = "en") -> list[KnowledgeChunk]:
    """Rank published local knowledge with lightweight bilingual lexical search."""
    candidates = list(
        KnowledgeChunk.objects.filter(
            source__is_enabled=True, source__status=KnowledgeSource.Status.INDEXED
        ).select_related("source")[:1500]
    )
    terms = set(re.findall(r"[a-z0-9\u0980-\u09ff]{2,}", question.casefold()))
    terms -= {
        "what",
        "how",
        "does",
        "do",
        "can",
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "please",
        "tell",
        "about",
        "is",
        "are",
        "was",
        "were",
        "of",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "i",
        "me",
        "my",
        "you",
        "your",
        "it",
        "be",
        "what's",
        "কী",
        "কি",
        "কীভাবে",
        "কিভাবে",
        "আমার",
        "আমাকে",
        "একটি",
        "এর",
        "জন্য",
        "করে",
        "বলুন",
    }
    if not terms:
        return []
    if terms.issubset({"turfbari", "turf"}) or "টার্ফবাড়ি" in question:
        overview = [chunk for chunk in candidates if chunk.source.key == f"homepage:overview:{language}"]
        if not overview:
            overview = [chunk for chunk in candidates if chunk.source.key == "homepage:overview:en"]
        return overview[:1]
    ranked = []
    for chunk in candidates:
        content = f"{chunk.source.title} {chunk.text}".casefold()
        content_terms = set(re.findall(r"[a-z0-9\u0980-\u09ff]{2,}", content))
        score = len(terms & content_terms) / len(terms)
        if question.casefold() in content:
            score += 1
        if chunk.source.language == language:
            score += 0.12
        if score >= 0.2:
            ranked.append((score, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1].source.title, item[1].ordinal))
    if not ranked and terms & {
        "turfbari",
        "turf",
        "platform",
        "booking",
        "bookings",
        "subscription",
        "sms",
        "টার্ফবাড়ি",
        "বুকিং",
        "সাবস্ক্রিপশন",
    }:
        overview = [chunk for chunk in candidates if chunk.source.key == f"homepage:overview:{language}"]
        if not overview:
            overview = [chunk for chunk in candidates if chunk.source.key == "homepage:overview:en"]
        return overview[:1]
    return [chunk for _, chunk in ranked[:limit]]


def local_answer(language: str, chunks: list[KnowledgeChunk], facts: list[str]) -> str:
    """Compose an extractive answer only from published knowledge and live DB facts."""
    paragraphs = list(facts)
    for chunk in chunks:
        text = re.sub(r"\s+", " ", chunk.text).strip()
        if text and text not in paragraphs:
            paragraphs.append(text)
    if not paragraphs:
        return (
            "প্রকাশিত TURFBARI তথ্যভাণ্ডারে এই প্রশ্নের নির্ভরযোগ্য উত্তর পাওয়া যায়নি। বিস্তারিত জানতে সাপোর্টের সাথে যোগাযোগ করুন।"
            if language == "bn"
            else (
                "I couldn't find a verified answer in TURFBARI's published information. "
                "Please contact support for help."
            )
        )
    lead = "প্রকাশিত TURFBARI তথ্য থেকে:" if language == "bn" else "From TURFBARI's published information:"
    return lead + "\n\n" + "\n\n".join(paragraphs[:4])[:3500]
