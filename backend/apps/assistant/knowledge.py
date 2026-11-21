"""Public, approved TURFBARI knowledge ingestion and retrieval."""

import hashlib
import math
import re

from django.utils import timezone

from apps.common.models import PlatformSettings
from apps.homepage.models import HomepageFAQ
from apps.notifications.models import SmsPricing
from apps.subscriptions.models import Plan

from .models import AssistantSettings, KnowledgeArticle, KnowledgeChunk, KnowledgeSource
from .provider import ProviderError, embed


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
    config,
    public_url: str = "",
) -> dict:
    content = _clean(content)
    digest = _hash(f"{title}\n{public_url}\n{content}")
    source, _ = KnowledgeSource.objects.get_or_create(
        key=key, defaults={"title": title, "language": language}
    )
    if source.content_hash == digest and source.status == KnowledgeSource.Status.INDEXED:
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
            vector = embed(chunk, config=config) if config.api_key_encrypted else []
            rows.append(
                KnowledgeChunk(
                    source=source, ordinal=ordinal, text=chunk, embedding=vector, content_hash=_hash(chunk)
                )
            )
        KnowledgeChunk.objects.bulk_create(rows)
        source.status = KnowledgeSource.Status.INDEXED
        source.indexed_at = timezone.now()
        source.save(update_fields=["status", "indexed_at", "updated_at"])
        return {"key": key, "status": source.status, "changed": True}
    except ProviderError as exc:
        source.status, source.error_code = KnowledgeSource.Status.FAILED, exc.code
        source.save(update_fields=["status", "error_code", "updated_at"])
        return {"key": key, "status": source.status, "changed": True}


def sync_knowledge() -> dict:
    """Rebuild published public sources and admin-published articles only. Drafts are excluded."""
    config = AssistantSettings.load()
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
            config=config,
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
                        config=config,
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
                config=config,
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
                config=config,
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
                        config=config,
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
                        config=config,
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


def live_facts(question: str) -> str:
    """Fetch live values for relevant questions; don't trust old price embeddings."""
    q = question.casefold()
    snippets = []
    if any(
        word in q for word in ("price", "cost", "plan", "subscription", "sms", "টাকা", "দাম", "খরচ", "সাবস্ক্রিপশন")
    ):
        plans = Plan.objects.filter(is_active=True, is_public=True).order_by("display_order", "months")
        snippets.extend(
            f"Live plan: {p.name}, BDT {p.price}, {p.months} months. {p.description}" for p in plans
        )
        sms = (
            SmsPricing.objects.filter(effective_from__lte=timezone.now())
            .order_by("-effective_from", "-id")
            .first()
        )
        if sms and any(word in q for word in ("sms", "segment", "এসএমএস")):
            snippets.append(f"Live SMS price: BDT {sms.price_per_segment} per billable segment.")
    if any(word in q for word in ("contact", "phone", "email", "যোগাযোগ", "ফোন")):
        s = PlatformSettings.load()
        if s.contact_enabled:
            snippets.extend(
                x
                for x in (
                    f"Public support phone: {s.contact_phone}"
                    if s.contact_show_phone and s.contact_phone
                    else "",
                    f"Public support email: {s.contact_email}"
                    if s.contact_show_email and s.contact_email
                    else "",
                    f"Facebook: {s.contact_facebook_url}"
                    if s.contact_show_facebook and s.contact_facebook_url
                    else "",
                )
                if x
            )
    return "\n".join(snippets)


def retrieve(question: str, limit: int = 5) -> list[KnowledgeChunk]:
    config = AssistantSettings.load()
    candidates = list(
        KnowledgeChunk.objects.filter(source__is_enabled=True, source__status=KnowledgeSource.Status.INDEXED)
        .exclude(source__key__startswith="sms-pricing:")
        .select_related("source")[:1500]
    )
    if not candidates:
        return []
    try:
        query_vector = embed(question, config=config) if config.api_key_encrypted else []
    except ProviderError:
        query_vector = []
    if query_vector:

        def similarity(chunk):
            vector = chunk.embedding
            if len(vector) != len(query_vector):
                return 0.0
            dot = sum(a * b for a, b in zip(vector, query_vector, strict=False))
            norm = math.sqrt(sum(x * x for x in vector)) * math.sqrt(sum(x * x for x in query_vector))
            return dot / norm if norm else 0.0

        candidates.sort(key=similarity, reverse=True)
        return [c for c in candidates[:limit] if similarity(c) > 0.12]
    words = {word for word in re.findall(r"[a-z0-9\u0980-\u09ff]{2,}", question.casefold())}
    ranked = sorted(
        candidates,
        key=lambda c: len(
            words & set(re.findall(r"[a-z0-9\u0980-\u09ff]{2,}", f"{c.source.title} {c.text}".casefold()))
        ),
        reverse=True,
    )
    return ranked[:limit]
