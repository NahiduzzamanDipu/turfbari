"""Public informational assistant and platform-admin configuration endpoints."""

import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
import socket
import uuid
from datetime import timedelta
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.audit.services import Category, record
from apps.common.permissions import IsPlatformAdmin

from .knowledge import live_facts, local_answer, retrieve, sync_knowledge
from .models import (
    AssistantFeedback,
    AssistantSettings,
    AssistantUsageDay,
    Conversation,
    ConversationMessage,
    KnowledgeArticle,
    KnowledgeChunk,
    KnowledgeSource,
    SuggestedQuestion,
)

log = logging.getLogger(__name__)


class AssistantThrottle(AnonRateThrottle):
    scope = "ai_chat"


class AssistantConversationThrottle(AnonRateThrottle):
    scope = "ai_chat_session"

    def get_cache_key(self, request, view):
        token = str(request.data.get("conversation_token", ""))
        if not token:
            return None
        return self.cache_format % {"scope": self.scope, "ident": _digest(token)}


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _conversation(request, data):
    try:
        conversation = Conversation.objects.get(pk=data.get("conversation_id"))
    except (Conversation.DoesNotExist, ValueError, TypeError):
        return None
    token = str(data.get("conversation_token") or "")
    if not token or not hmac.compare_digest(conversation.token_hash, _digest(token)):
        return None
    if conversation.updated_at < timezone.now() - timedelta(days=AssistantSettings.load().retention_days):
        return None
    if conversation.user_id and (
        not request.user.is_authenticated or conversation.user_id != request.user.pk
    ):
        return None
    return conversation


def _safe_routes(question: str, language: str) -> list[dict]:
    q = question.casefold()
    if any(word in q for word in ("register", "registration", "রেজিস্টার", "নিবন্ধন")):
        return [
            {"label": "Register your turf" if language == "en" else "টার্ফ নিবন্ধন", "url": "/register-turf"}
        ]
    if any(word in q for word in ("demo", "ডেমো")):
        return [
            {"label": "Try the demo" if language == "en" else "ডেমো দেখুন", "url": "/demo-booking"},
            {"label": "Owner demo" if language == "en" else "মালিক ডেমো", "url": "/demo-account"},
        ]
    if any(word in q for word in ("plan", "subscription", "price", "pricing", "প্ল্যান", "সাবস্ক্রিপশন", "দাম")):
        return [{"label": "Subscription plans" if language == "en" else "সাবস্ক্রিপশন প্ল্যান", "url": "/#plans"}]
    if any(word in q for word in ("terms", "privacy", "policy", "শর্ত", "গোপনীয়তা")):
        return [{"label": "Legal policies" if language == "en" else "নীতিমালা", "url": "/legal"}]
    if any(word in q for word in ("contact", "support", "যোগাযোগ", "সহায়তা")):
        return [{"label": "Contact TURFBARI" if language == "en" else "যোগাযোগ", "url": "/#contact"}]
    return []


def _redact(message: str) -> str:
    message = re.sub(r"(?i)[\w.+-]+@[\w.-]+\.[a-z]{2,}", "[email redacted]", message)
    message = re.sub(r"(?<!\w)(?:\+?\d[\d\s()-]{8,}\d)(?!\w)", "[phone or number redacted]", message)
    message = re.sub(r"(?i)(password|passcode)\s*[:=]\s*\S+", r"\1=[redacted]", message)
    message = re.sub(r"(?i)(trx(?:id)?|transaction\s*id)\s*[:=]?\s*[a-z0-9-]{5,}", r"\1 [redacted]", message)
    return message[:2000]


class PublicAssistantStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        config = AssistantSettings.load()
        questions = SuggestedQuestion.objects.filter(is_active=True)
        return Response(
            {
                "enabled": config.enabled,
                "available": config.enabled,
                "service_mode": "local_knowledge",
                "display_name": config.display_name,
                "welcome": {
                    "en": config.welcome_en,
                    "bn": config.welcome_bn
                    or "টার্ফবাড়ির বুকিং, সাবস্ক্রিপশন, SMS এবং অ্যাকাউন্ট সম্পর্কে আমাকে জিজ্ঞাসা করুন।",
                },
                "default_language": config.default_language,
                "service_state": "ready" if config.enabled else "disabled",
                "suggested_questions": [{"en": q.question_en, "bn": q.question_bn} for q in questions],
                "privacy_note": (
                    "Do not send passwords, payment transaction details, or private customer information."
                ),
            }
        )


class PublicConversationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AssistantThrottle, AssistantConversationThrottle]

    def post(self, request):
        config = AssistantSettings.load()
        if not config.enabled:
            return Response(
                {"error": "Assistant is currently unavailable."}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        message = str(request.data.get("message", "")).strip()
        language = request.data.get("language", "en")
        if language not in {"en", "bn"}:
            language = "en"
        if not message or len(message) > 2000:
            return Response(
                {"error": "Enter a message up to 2,000 characters."}, status=status.HTTP_400_BAD_REQUEST
            )
        if re.search(
            r"(?i)(password|passcode|bKash.{0,20}(?:trx|transaction)|transaction\s*id)\s*[:=]\s*\S+", message
        ):
            return Response(
                {
                    "error": (
                        "Please do not send passwords or payment credentials here. "
                        "Contact support through the official contact page."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        conversation = _conversation(request, request.data)
        if conversation is None:
            return Response(
                {"error": "Conversation expired. Start a new conversation."}, status=status.HTTP_404_NOT_FOUND
            )
        if conversation.messages.count() >= 40:
            return Response(
                {"error": "This conversation reached its message limit. Start a new conversation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            client_message_id = uuid.UUID(str(request.data.get("client_message_id", "")))
        except (ValueError, TypeError, AttributeError):
            return Response({"error": "A valid client message ID is required."}, status=400)
        with transaction.atomic():
            locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
            existing = ConversationMessage.objects.filter(
                conversation=locked,
                role=ConversationMessage.Role.USER,
                client_message_id=client_message_id,
            ).first()
            if existing:
                reply = getattr(existing, "assistant_reply", None)
                if reply:
                    sources = KnowledgeSource.objects.filter(
                        pk__in=reply.source_ids,
                        is_enabled=True,
                        status=KnowledgeSource.Status.INDEXED,
                    )
                    return Response(
                        {
                            "message": {"id": reply.pk, "content": reply.content},
                            "links": _safe_routes(message, language),
                            "sources": [
                                {
                                    "title": source.title,
                                    "url": source.public_url,
                                    "version": source.version,
                                    "language": source.language,
                                }
                                for source in sources
                                if source.public_url.startswith("/")
                                and not source.public_url.startswith("//")
                            ],
                            "duplicate": True,
                        }
                    )
                if existing.status == "processing":
                    return Response({"error": "This message is already being processed."}, status=409)
            day = timezone.localdate()
            usage_day, _ = AssistantUsageDay.objects.get_or_create(day=day)
            usage_day = AssistantUsageDay.objects.select_for_update().get(day=day)
            if usage_day.message_count >= config.daily_message_limit:
                return Response(
                    {"error": "Daily assistant usage limit reached. Please contact TURFBARI support."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            usage_day.message_count += 1
            usage_day.save(update_fields=["message_count", "updated_at"])
            if existing:
                existing.status = "processing"
                existing.save(update_fields=["status"])
                user_message = existing
            else:
                safe_message = _redact(message)
                user_message = ConversationMessage.objects.create(
                    conversation=locked,
                    role=ConversationMessage.Role.USER,
                    client_message_id=client_message_id,
                    content=safe_message,
                    status="processing",
                )
        safe_message = user_message.content
        try:
            if not KnowledgeChunk.objects.filter(
                source__key="homepage:overview:en",
                source__is_enabled=True,
                source__status=KnowledgeSource.Status.INDEXED,
            ).exists():
                sync_knowledge()
            previous_questions = list(
                conversation.messages.filter(role=ConversationMessage.Role.USER)
                .exclude(pk=user_message.pk)
                .order_by("-created_at")[:2]
                .values_list("content", flat=True)
            )
            search_query = safe_message
            if len(safe_message.split()) <= 5 and previous_questions:
                search_query = " ".join([*reversed(previous_questions), safe_message])
            chunks = retrieve(search_query, language=language)
            facts = live_facts(search_query)
            answer = local_answer(language, chunks, facts)
            reply = ConversationMessage.objects.create(
                conversation=conversation,
                role="assistant",
                in_reply_to=user_message,
                content=answer,
                source_ids=[str(c.source_id) for c in chunks],
            )
            citations = [
                {
                    "title": chunk.source.title,
                    "url": chunk.source.public_url,
                    "version": chunk.source.version,
                    "language": chunk.source.language,
                }
                for chunk in chunks
                if chunk.source.public_url.startswith("/") and not chunk.source.public_url.startswith("//")
            ]
            conversation.language = language
            conversation.save(update_fields=["language", "updated_at"])
            return Response(
                {
                    "message": {"id": reply.pk, "content": reply.content},
                    "links": _safe_routes(message, language),
                    "sources": citations,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Local assistant request failed (%s).", type(exc).__name__)
            user_message.status = "failed"
            user_message.save(update_fields=["status"])
            return Response(
                {"error": "The assistant encountered a temporary issue. Please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PublicConversationStartView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AssistantThrottle, AssistantConversationThrottle]

    def post(self, request):
        language = request.data.get("language", "en")
        if language not in {"en", "bn"}:
            language = "en"
        token = secrets.token_urlsafe(32)
        conversation = Conversation.objects.create(
            token_hash=_digest(token),
            user=request.user if request.user.is_authenticated else None,
            language=language,
        )
        return Response({"conversation_id": str(conversation.pk), "conversation_token": token}, status=201)


class PublicConversationClearView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AssistantThrottle, AssistantConversationThrottle]

    def post(self, request):
        conversation = _conversation(request, request.data)
        if conversation is None:
            return Response({"error": "Conversation not found."}, status=404)
        conversation.messages.all().delete()
        conversation.cleared_at = timezone.now()
        conversation.save(update_fields=["cleared_at", "updated_at"])
        return Response({"cleared": True})


class PublicFeedbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AssistantThrottle]

    def post(self, request):
        conversation = _conversation(request, request.data)
        if conversation is None:
            return Response({"error": "Conversation not found."}, status=404)
        message = conversation.messages.filter(
            pk=request.data.get("message_id"), role=ConversationMessage.Role.ASSISTANT
        ).first()
        if not message:
            return Response({"error": "Assistant response not found."}, status=404)
        helpful = request.data.get("helpful")
        if not isinstance(helpful, bool):
            return Response({"error": "Feedback must be helpful or not helpful."}, status=400)
        AssistantFeedback.objects.get_or_create(message=message, defaults={"helpful": helpful})
        return Response({"saved": True}, status=201)


class AdminAssistantSettingsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        c = AssistantSettings.load()
        return Response(
            {
                "enabled": c.enabled,
                "display_name": c.display_name,
                "welcome_en": c.welcome_en,
                "welcome_bn": c.welcome_bn,
                "default_language": c.default_language,
                "context_messages": c.context_messages,
                "daily_message_limit": c.daily_message_limit,
                "retention_days": c.retention_days,
                "service_mode": "local_knowledge",
            }
        )

    def put(self, request):
        c = AssistantSettings.load()
        values = request.data
        enabled = values.get("enabled", c.enabled)
        language = values.get("default_language", c.default_language)
        if not isinstance(enabled, bool) or language not in {"en", "bn"}:
            return Response({"error": "Invalid assistant enabled or language setting."}, status=400)
        try:
            context_messages = min(max(int(values.get("context_messages", c.context_messages)), 2), 20)
            daily_limit = min(max(int(values.get("daily_message_limit", c.daily_message_limit)), 1), 100000)
            retention = min(max(int(values.get("retention_days", c.retention_days)), 1), 365)
        except (TypeError, ValueError):
            return Response({"error": "Assistant limits must be valid numbers."}, status=400)
        c.enabled = enabled
        c.display_name = str(values.get("display_name", c.display_name)).strip()[:80] or "TURFBARI Assistant"
        c.welcome_en = str(values.get("welcome_en", c.welcome_en))[:2000]
        c.welcome_bn = str(values.get("welcome_bn", c.welcome_bn))[:2000]
        c.default_language = language
        c.context_messages = context_messages
        c.daily_message_limit = daily_limit
        c.retention_days = retention
        c.save()
        KnowledgeSource.objects.filter(is_enabled=True).update(status=KnowledgeSource.Status.PENDING)
        try:
            from .tasks import reindex_knowledge

            reindex_knowledge.delay()
        except Exception:  # noqa: BLE001 - the system tick will process pending sources
            log.info("Local assistant knowledge re-index queued for the next system tick.")
        record(
            "platform.ai_settings_updated",
            "Updated local assistant settings",
            category=Category.PLATFORM,
            request=request,
            target=c,
        )
        return self.get(request)


class AdminKnowledgeArticlesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk=None):
        if pk:
            article = KnowledgeArticle.objects.filter(pk=pk).first()
            if not article:
                return Response(status=404)
            return Response(_article_data(article))
        return Response([_article_data(a) for a in KnowledgeArticle.objects.all()])

    def post(self, request, pk=None):
        article = KnowledgeArticle.objects.filter(pk=pk).first() if pk else KnowledgeArticle()
        if article is None:
            return Response(status=404)
        for field in ("title_en", "title_bn", "body_en", "body_bn"):
            if field in request.data:
                setattr(article, field, str(request.data[field])[:20000])
        published = request.data.get("is_published", article.is_published)
        if not isinstance(published, bool):
            return Response({"error": "Publication status must be boolean."}, status=400)
        article.is_published = published
        article.updated_by = request.user
        article.save()
        record(
            "platform.ai_knowledge_saved",
            "Saved AI knowledge article",
            category=Category.PLATFORM,
            request=request,
            target=article,
        )
        return Response(_article_data(article), status=201 if not pk else 200)

    def delete(self, request, pk=None):
        article = KnowledgeArticle.objects.filter(pk=pk).first()
        if not article:
            return Response(status=404)
        record(
            "platform.ai_knowledge_deleted",
            "Deleted AI knowledge article",
            category=Category.PLATFORM,
            request=request,
            target=article,
        )
        article.delete()
        return Response(status=204)


def _article_data(article):
    return {
        "id": str(article.pk),
        "title_en": article.title_en,
        "title_bn": article.title_bn,
        "body_en": article.body_en,
        "body_bn": article.body_bn,
        "is_published": article.is_published,
        "source_type": article.source_type,
        "source_url": article.source_url,
        "updated_at": article.updated_at,
    }


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = data.strip()
            if value:
                self.parts.append(value)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_public_site(url: str) -> str:
    parsed = urlsplit(url)
    configured = urlsplit(settings.FRONTEND_URL)
    if (
        parsed.scheme != "https"
        or parsed.hostname != configured.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Only HTTPS pages on the configured public site can be imported.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("The configured public host did not resolve.") from None
    if not addresses or any(
        ipaddress.ip_address(item[4][0]).is_private
        or ipaddress.ip_address(item[4][0]).is_loopback
        or ipaddress.ip_address(item[4][0]).is_link_local
        or ipaddress.ip_address(item[4][0]).is_reserved
        for item in addresses
    ):
        raise ValueError("The configured public host did not resolve to a public address.")
    request = Request(  # noqa: S310 - URL host and scheme are allowlisted and checked above
        url, headers={"User-Agent": "TurfBari-Knowledge-Indexer/1.0", "Accept": "text/html,text/plain"}
    )
    try:
        with build_opener(_NoRedirect).open(request, timeout=8) as response:  # noqa: S310 - host and scheme allowlisted above
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "text/markdown"}:
                raise ValueError("Only HTML, plain text, or Markdown pages can be imported.")
            body = response.read(1_000_001)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise ValueError("The public page could not be fetched safely.") from None
    if len(body) > 1_000_000:
        raise ValueError("Imported pages must be smaller than 1 MB.")
    text = body.decode("utf-8", errors="replace")
    if content_type == "text/html":
        parser = _TextExtractor()
        parser.feed(text)
        text = "\n".join(parser.parts)
    if not text.strip():
        raise ValueError("The page did not contain readable text.")
    return text[:20000]


class AdminKnowledgeImportView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        title = str(request.data.get("title_en", "")).strip()[:200]
        title_bn = str(request.data.get("title_bn", "")).strip()[:200]
        if not title:
            return Response({"error": "English title is required."}, status=400)
        uploaded = request.FILES.get("file")
        source_url = str(request.data.get("source_url", "")).strip()
        if uploaded:
            if uploaded.size > 1_000_000 or not uploaded.name.lower().endswith((".txt", ".md", ".markdown")):
                return Response(
                    {"error": "Upload a UTF-8 .txt or Markdown file smaller than 1 MB."}, status=400
                )
            try:
                body = uploaded.read(1_000_001).decode("utf-8")
            except UnicodeDecodeError:
                return Response({"error": "The document must be UTF-8 encoded text."}, status=400)
            if not body.strip() or "\x00" in body:
                return Response({"error": "The uploaded document has no readable text."}, status=400)
            source_type = "upload"
            source_url = ""
        elif source_url:
            try:
                body = _fetch_public_site(source_url)
            except ValueError as exc:
                return Response({"error": str(exc)}, status=400)
            source_type = "url"
        else:
            return Response(
                {"error": "Choose a .txt/Markdown file or provide a public page URL."}, status=400
            )
        article = KnowledgeArticle.objects.create(
            title_en=title,
            title_bn=title_bn,
            body_en=body,
            is_published=False,
            source_type=source_type,
            source_url=source_url,
            updated_by=request.user,
        )
        record(
            "platform.ai_knowledge_imported",
            "Imported an AI knowledge source draft",
            category=Category.PLATFORM,
            request=request,
            target=article,
            data={"source_type": source_type},
        )
        return Response(_article_data(article), status=201)


class AdminKnowledgeSourcesView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk=None):
        sources = KnowledgeSource.objects.annotate(chunk_count=Count("chunks"))
        if pk:
            sources = sources.filter(pk=pk)
        return Response(
            [
                {
                    "id": str(s.pk),
                    "key": s.key,
                    "title": s.title,
                    "language": s.language,
                    "source_type": s.source_type,
                    "version": s.version,
                    "status": s.status,
                    "indexed_at": s.indexed_at,
                    "error_code": s.error_code,
                    "is_enabled": s.is_enabled,
                    "public_url": s.public_url,
                    "chunks": s.chunk_count,
                }
                for s in sources
            ]
        )

    def patch(self, request, pk=None):
        source = KnowledgeSource.objects.filter(pk=pk).first()
        if not source:
            return Response(status=404)
        if "is_enabled" in request.data:
            source.is_enabled = bool(request.data["is_enabled"])
            source.save(update_fields=["is_enabled", "updated_at"])
        record(
            "platform.ai_source_updated",
            "Updated AI knowledge source visibility",
            category=Category.PLATFORM,
            request=request,
            target=source,
        )
        return Response(self.get(request, pk).data)


class AdminKnowledgeReindexView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request):
        from .tasks import reindex_knowledge

        KnowledgeSource.objects.filter(is_enabled=True).update(status=KnowledgeSource.Status.PENDING)
        try:
            result = reindex_knowledge.delay()
            task_id = result.id
            queued = True
        except Exception:  # noqa: BLE001
            # The lightweight hosting profile runs indexing from the periodic system tick.
            task_id, queued = None, False
        record(
            "platform.ai_reindex_requested",
            "Requested AI knowledge re-index",
            category=Category.PLATFORM,
            request=request,
        )
        return Response(
            {"queued": queued, "task_id": task_id, "pending_background_tick": not queued}, status=202
        )


class AdminSuggestedQuestionsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, pk=None):
        qs = SuggestedQuestion.objects.all()
        if pk:
            qs = qs.filter(pk=pk)
        return Response(
            [
                {
                    "id": str(q.pk),
                    "question_en": q.question_en,
                    "question_bn": q.question_bn,
                    "display_order": q.display_order,
                    "is_active": q.is_active,
                }
                for q in qs
            ]
        )

    def post(self, request, pk=None):
        item = SuggestedQuestion.objects.filter(pk=pk).first() if pk else SuggestedQuestion()
        if item is None:
            return Response(status=404)
        item.question_en = str(request.data.get("question_en", item.question_en)).strip()[:240]
        item.question_bn = str(request.data.get("question_bn", item.question_bn)).strip()[:240]
        try:
            item.display_order = max(0, min(int(request.data.get("display_order", item.display_order)), 1000))
        except (TypeError, ValueError):
            return Response({"error": "Display order must be a number."}, status=400)
        active = request.data.get("is_active", item.is_active)
        if not isinstance(active, bool):
            return Response({"error": "Active status must be boolean."}, status=400)
        item.is_active = active
        if not item.question_en:
            return Response({"error": "English suggested question is required."}, status=400)
        item.save()
        record(
            "platform.ai_suggested_question_saved",
            "Saved AI suggested question",
            category=Category.PLATFORM,
            request=request,
            target=item,
        )
        return Response(
            {
                "id": str(item.pk),
                "question_en": item.question_en,
                "question_bn": item.question_bn,
                "display_order": item.display_order,
                "is_active": item.is_active,
            },
            status=201 if not pk else 200,
        )

    def delete(self, request, pk=None):
        item = SuggestedQuestion.objects.filter(pk=pk).first()
        if not item:
            return Response(status=404)
        record(
            "platform.ai_suggested_question_deleted",
            "Deleted AI suggested question",
            category=Category.PLATFORM,
            request=request,
            target=item,
        )
        item.delete()
        return Response(status=204)


class AdminAssistantAnalyticsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        today = timezone.localdate()
        messages = ConversationMessage.objects.filter(created_at__date=today)
        month_messages = ConversationMessage.objects.filter(
            created_at__year=today.year, created_at__month=today.month
        )
        conversations = Conversation.objects.all()
        recent = list(
            conversations.prefetch_related(
                Prefetch(
                    "messages",
                    queryset=ConversationMessage.objects.filter(role="assistant"),
                    to_attr="assistant_responses",
                )
            ).order_by("-updated_at")[:50]
        )
        return Response(
            {
                "conversations": conversations.count(),
                "messages_today": messages.count(),
                "messages_this_month": month_messages.count(),
                "user_messages_today": messages.filter(role="user").count(),
                "responses_today": messages.filter(role="assistant").count(),
                "failed_today": messages.exclude(status="ok").count(),
                "bengali_conversations": conversations.filter(language="bn").count(),
                "english_conversations": conversations.filter(language="en").count(),
                "feedback_helpful": AssistantFeedback.objects.filter(helpful=True).count(),
                "feedback_not_helpful": AssistantFeedback.objects.filter(helpful=False).count(),
                "recent": [
                    {
                        "id": str(conversation.pk),
                        "language": conversation.language,
                        "message_count": conversation.messages.count(),
                        "updated_at": conversation.updated_at,
                        "source_count": sum(
                            len(message.source_ids or []) for message in conversation.assistant_responses
                        ),
                    }
                    for conversation in recent
                ],
            }
        )
