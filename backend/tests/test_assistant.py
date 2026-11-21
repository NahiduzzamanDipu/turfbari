from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.assistant.knowledge import live_facts, sync_knowledge
from apps.assistant.models import (
    AssistantSettings,
    AssistantUsageDay,
    ConversationMessage,
    KnowledgeArticle,
    KnowledgeChunk,
    KnowledgeSource,
)

pytestmark = pytest.mark.django_db


def start_conversation(language="en"):
    response = APIClient().post("/api/public/assistant/conversations/", {"language": language}, format="json")
    assert response.status_code == 201
    return response.json()


def add_source(key, title, text, language="en", url="/help"):
    source = KnowledgeSource.objects.create(
        key=key,
        title=title,
        language=language,
        version="v1",
        public_url=url,
        status=KnowledgeSource.Status.INDEXED,
    )
    KnowledgeChunk.objects.create(source=source, ordinal=0, text=text, content_hash="test")
    return source


def ask(session, message, language="en", client=None, request_id=None):
    return (client or APIClient()).post(
        "/api/public/assistant/messages/",
        {
            **session,
            "message": message,
            "language": language,
            "client_message_id": str(request_id or uuid4()),
        },
        format="json",
    )


def test_status_reports_local_knowledge_service_ready_without_provider_configuration():
    response = APIClient().get("/api/public/assistant/status/")
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["service_mode"] == "local_knowledge"
    assert response.json()["service_state"] == "ready"
    assert response.json()["welcome"]["bn"]
    assert "api_key" not in str(response.json())
    assert not hasattr(AssistantSettings.load(), "api_key_encrypted")


def test_chat_returns_published_local_source_and_redacts_personal_details():
    source = add_source(
        "faq:local-1", "Booking guide", "Customers book an available turf slot from its public booking page."
    )
    session = start_conversation()
    response = ask(
        session, "How do customers book a turf slot? Contact me at player@example.com, 01712345678"
    )
    assert response.status_code == 200
    body = response.json()
    assert "public booking page" in body["message"]["content"]
    assert body["sources"][0]["title"] == source.title
    saved = ConversationMessage.objects.get(role="user")
    assert "player@example.com" not in saved.content
    assert "01712345678" not in saved.content
    assistant = ConversationMessage.objects.get(role="assistant")
    assert assistant.source_ids == [str(source.pk)]


def test_first_public_question_builds_empty_local_index_automatically():
    response = ask(start_conversation(), "What is TURFBARI?")
    assert response.status_code == 200
    assert "TURFBARI" in response.json()["message"]["content"]
    assert KnowledgeSource.objects.filter(key="homepage:overview:en").exists()


def test_bengali_answer_uses_bengali_published_material():
    source = add_source(
        "faq:bn-1",
        "\u09ac\u09c1\u0995\u09bf\u0982 \u0997\u09be\u0987\u09a1",
        (
            "\u0997\u09cd\u09b0\u09be\u09b9\u0995\u09b0\u09be "
            "\u09aa\u09cd\u09b0\u0995\u09be\u09b6\u09cd\u09af "
            "\u09ac\u09c1\u0995\u09bf\u0982 \u09aa\u09be\u09a4\u09be "
            "\u09a5\u09c7\u0995\u09c7 \u09b8\u09cd\u09b2\u099f "
            "\u09ac\u09c1\u0995 \u0995\u09b0\u09c7\u09a8\u0964"
        ),
        language="bn",
    )
    session = start_conversation("bn")
    response = ask(
        session,
        "\u09b8\u09cd\u09b2\u099f \u0995\u09c0\u09ad\u09be\u09ac\u09c7 "
        "\u09ac\u09c1\u0995 \u0995\u09b0\u09ac?",
        language="bn",
    )
    assert response.status_code == 200
    assert response.json()["message"]["content"].startswith(
        "\u09aa\u09cd\u09b0\u0995\u09be\u09b6\u09bf\u09a4 TURFBARI"
    )
    assert response.json()["sources"][0]["title"] == source.title


def test_follow_up_short_question_uses_recent_user_context():
    source = add_source(
        "faq:followup", "SMS wallet", "SMS wallet recharge adds money to the account before SMS can be sent."
    )
    session = start_conversation()
    client = APIClient()
    first = ask(session, "How does SMS wallet recharge work?", client=client)
    second = ask(session, "How much?", client=client)
    assert first.status_code == second.status_code == 200
    assert source.title in [item["title"] for item in second.json()["sources"]]


def test_daily_limit_is_enforced_with_usage_counter():
    config = AssistantSettings.load()
    config.daily_message_limit = 1
    config.save()
    client = APIClient()
    session = start_conversation()
    first = ask(session, "Hello", client=client)
    second = ask(session, "What is TURFBARI?", client=client)
    assert first.status_code == 200
    assert second.status_code == 429
    assert AssistantUsageDay.objects.get().message_count == 1


def test_duplicate_client_message_id_reuses_local_answer():
    source = add_source(
        "faq:dup", "Platform overview", "TURFBARI helps turf owners manage bookings and public pages."
    )
    session = start_conversation()
    request_id = uuid4()
    first = ask(session, "What is TURFBARI?", request_id=request_id)
    second = ask(session, "What is TURFBARI?", request_id=request_id)
    assert first.status_code == second.status_code == 200
    assert second.json()["duplicate"] is True
    assert source.title in [item["title"] for item in first.json()["sources"]]
    assert ConversationMessage.objects.filter(role="user").count() == 1
    assert ConversationMessage.objects.filter(role="assistant").count() == 1
    assert AssistantUsageDay.objects.get().message_count == 1


def test_unknown_question_returns_honest_no_match_message():
    response = ask(start_conversation(), "What is the capital of Iceland?")
    assert response.status_code == 200
    assert "couldn't find a verified answer" in response.json()["message"]["content"]
    assert response.json()["sources"] == []


def test_sensitive_message_is_rejected_before_storage():
    response = ask(start_conversation(), "My password: secret123")
    assert response.status_code == 400
    assert ConversationMessage.objects.count() == 0


def test_unpublished_knowledge_article_is_not_indexed():
    article = KnowledgeArticle.objects.create(
        title_en="Private draft", body_en="This draft must never be indexed", is_published=False
    )
    sync_knowledge()
    assert not KnowledgeSource.objects.filter(key=f"article:{article.pk}:en").exists()


def test_published_help_article_is_indexed_and_live_prices_are_authoritative():
    article = KnowledgeArticle.objects.create(
        title_en="Booking help", body_en="Customers use a turf public booking page.", is_published=True
    )
    sync_knowledge()
    source = KnowledgeSource.objects.get(key=f"article:{article.pk}:en")
    assert source.status == KnowledgeSource.Status.INDEXED
    assert source.chunks.exists()
    assert isinstance(live_facts("What does SMS cost?"), list)


def test_admin_settings_are_provider_free_and_platform_admin_only():
    response = APIClient().get("/api/admin/assistant/settings/")
    assert response.status_code in {401, 403}
    admin = get_user_model().objects.create_superuser("assistant-admin@example.test", "SecurePass123!")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.get("/api/admin/assistant/settings/")
    assert response.status_code == 200
    assert response.json()["service_mode"] == "local_knowledge"
    assert "api_key" not in response.json()
    update = client.put(
        "/api/admin/assistant/settings/",
        {"enabled": True, "default_language": "bn", "daily_message_limit": 50},
        format="json",
    )
    assert update.status_code == 200
    assert update.json()["daily_message_limit"] == 50
    assert client.post("/api/admin/assistant/test/", {}, format="json").status_code == 404


def test_admin_knowledge_import_is_draft_and_external_url_is_rejected():
    admin = get_user_model().objects.create_superuser("knowledge-admin@example.test", "SecurePass123!")
    client = APIClient()
    client.force_authenticate(admin)
    file = SimpleUploadedFile("guide.md", b"# Public guide\nApproved content", content_type="text/markdown")
    uploaded = client.post(
        "/api/admin/assistant/import/", {"title_en": "Imported guide", "file": file}, format="multipart"
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["is_published"] is False
    assert uploaded.json()["source_type"] == "upload"
    external = client.post(
        "/api/admin/assistant/import/",
        {"title_en": "Remote", "source_url": "https://example.invalid/"},
        format="json",
    )
    assert external.status_code == 400
    assert KnowledgeArticle.objects.count() == 1
