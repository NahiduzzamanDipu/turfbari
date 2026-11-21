import uuid

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
    KnowledgeSource,
)
from apps.assistant.provider import ProviderError
from apps.common.crypto import decrypt

pytestmark = pytest.mark.django_db


def start_conversation(language="en"):
    response = APIClient().post("/api/public/assistant/conversations/", {"language": language}, format="json")
    assert response.status_code == 201
    return response.json()


def test_public_status_does_not_expose_provider_credentials():
    config = AssistantSettings.load()
    config.api_key_encrypted = "encrypted-secret"
    config.save()
    response = APIClient().get("/api/public/assistant/status/")
    assert response.status_code == 200
    assert response.json()["available"] is False  # invalid encrypted data is never treated as ready
    assert response.json()["welcome"]["bn"]
    assert "api_key" not in str(response.json())


def test_conversation_token_is_required_and_bound_to_user(monkeypatch):
    session = start_conversation()
    config = AssistantSettings.load()
    config.api_key_encrypted = ""
    config.save()
    client = APIClient()
    response = client.post(
        "/api/public/assistant/messages/",
        {
            **session,
            "message": "Hello",
            "conversation_token": "wrong",
            "client_message_id": str(uuid.uuid4()),
        },
        format="json",
    )
    assert response.status_code == 404
    assert ConversationMessage.objects.count() == 0


def test_chat_uses_provider_and_redacts_personal_details(monkeypatch):
    config = AssistantSettings.load()
    config.api_key_encrypted = ""
    config.save()
    session = start_conversation()
    captured = {}

    def fake_complete(messages, *, config):
        captured["messages"] = messages
        return "TURFBARI helps turf businesses manage bookings.", {
            "prompt_tokens": 10,
            "completion_tokens": 8,
        }

    monkeypatch.setattr("apps.assistant.views.complete", fake_complete)
    monkeypatch.setattr("apps.assistant.views.retrieve", lambda question: [])
    monkeypatch.setattr("apps.assistant.views.live_facts", lambda question: "")
    response = APIClient().post(
        "/api/public/assistant/messages/",
        {
            **session,
            "message": "Please contact me at player@example.com, phone 01712345678",
            "client_message_id": str(uuid.uuid4()),
        },
        format="json",
    )
    assert response.status_code == 200
    saved = ConversationMessage.objects.get(role="user")
    assert "player@example.com" not in saved.content
    assert "01712345678" not in saved.content
    assert "player@example.com" not in str(captured["messages"])
    assert response.json()["message"]["content"].startswith("TURFBARI")
    assistant_message = ConversationMessage.objects.get(role="assistant")
    assert assistant_message.prompt_tokens == 10
    assert assistant_message.completion_tokens == 8


def test_bengali_preference_is_forwarded_as_provider_instruction(monkeypatch):
    config = AssistantSettings.load()
    config.save()
    session = start_conversation("bn")
    captured = {}

    def fake_complete(messages, *, config):
        captured["system"] = messages[0]["content"]
        return "বাংলায় উত্তর", {}

    monkeypatch.setattr("apps.assistant.views.complete", fake_complete)
    monkeypatch.setattr("apps.assistant.views.retrieve", lambda question: [])
    monkeypatch.setattr("apps.assistant.views.live_facts", lambda question: "")
    response = APIClient().post(
        "/api/public/assistant/messages/",
        {**session, "message": "TURFBARI কী?", "language": "bn", "client_message_id": str(uuid.uuid4())},
        format="json",
    )
    assert response.status_code == 200
    assert "Respond primarily in Bengali" in captured["system"]


def test_daily_limit_is_enforced_with_usage_counter(monkeypatch):
    config = AssistantSettings.load()
    config.daily_message_limit = 1
    config.save()
    monkeypatch.setattr("apps.assistant.views.complete", lambda messages, *, config: ("OK", {}))
    monkeypatch.setattr("apps.assistant.views.retrieve", lambda question: [])
    monkeypatch.setattr("apps.assistant.views.live_facts", lambda question: "")
    client = APIClient()
    session = start_conversation()
    first = client.post(
        "/api/public/assistant/messages/",
        {**session, "message": "Hello", "client_message_id": str(uuid.uuid4())},
        format="json",
    )
    second = client.post(
        "/api/public/assistant/messages/",
        {**session, "message": "What is TURFBARI?", "client_message_id": str(uuid.uuid4())},
        format="json",
    )
    assert first.status_code == 200
    assert second.status_code == 429
    assert AssistantUsageDay.objects.get().message_count == 1


def test_duplicate_client_message_id_reuses_completed_response(monkeypatch):
    config = AssistantSettings.load()
    config.daily_message_limit = 10
    config.save()
    calls = []

    def fake_complete(messages, *, config):
        calls.append(1)
        return "Grounded TURFBARI answer.", {"prompt_tokens": 5, "completion_tokens": 4}

    monkeypatch.setattr("apps.assistant.views.complete", fake_complete)
    monkeypatch.setattr("apps.assistant.views.retrieve", lambda question: [])
    monkeypatch.setattr("apps.assistant.views.live_facts", lambda question: "")
    session = start_conversation()
    payload = {
        **session,
        "message": "What is TURFBARI?",
        "client_message_id": str(uuid.uuid4()),
    }
    client = APIClient()
    first = client.post("/api/public/assistant/messages/", payload, format="json")
    second = client.post("/api/public/assistant/messages/", payload, format="json")
    assert first.status_code == 200
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert calls == [1]
    assert AssistantUsageDay.objects.get().message_count == 1


def test_provider_failure_can_retry_same_client_message_without_duplicate_user_row(monkeypatch):
    config = AssistantSettings.load()
    config.daily_message_limit = 10
    config.save()
    session = start_conversation()
    request_data = {
        **session,
        "message": "Can you help?",
        "client_message_id": str(uuid.uuid4()),
    }
    monkeypatch.setattr("apps.assistant.views.retrieve", lambda question: [])
    monkeypatch.setattr("apps.assistant.views.live_facts", lambda question: "")
    monkeypatch.setattr(
        "apps.assistant.views.complete",
        lambda messages, *, config: (_ for _ in ()).throw(ProviderError("provider_unavailable")),
    )
    client = APIClient()
    failed = client.post("/api/public/assistant/messages/", request_data, format="json")
    assert failed.status_code == 503
    monkeypatch.setattr("apps.assistant.views.complete", lambda messages, *, config: ("Recovered answer", {}))
    retried = client.post("/api/public/assistant/messages/", request_data, format="json")
    assert retried.status_code == 200
    assert ConversationMessage.objects.filter(role="user").count() == 1
    assert ConversationMessage.objects.filter(role="assistant").count() == 1


def test_sensitive_message_is_rejected_before_storage():
    session = start_conversation()
    response = APIClient().post(
        "/api/public/assistant/messages/",
        {
            **session,
            "message": "My password: secret123",
            "client_message_id": str(uuid.uuid4()),
        },
        format="json",
    )
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
        title_en="Booking help", body_en="Customers use a turf's public booking page.", is_published=True
    )
    sync_knowledge()
    source = KnowledgeSource.objects.get(key=f"article:{article.pk}:en")
    assert source.status == KnowledgeSource.Status.INDEXED
    assert source.chunks.exists()
    assert "Live SMS price" in live_facts("What does SMS cost?")


def test_admin_settings_encrypt_key_and_require_platform_admin():
    response = APIClient().put(
        "/api/admin/assistant/settings/",
        {"api_key": "sk-test-secret", "base_url": "https://api.openai.com/v1"},
        format="json",
    )
    assert response.status_code in {401, 403}
    admin = get_user_model().objects.create_superuser("assistant-admin@example.test", "SecurePass123!")
    client = APIClient()
    client.force_authenticate(admin)
    response = client.put(
        "/api/admin/assistant/settings/",
        {"api_key": "sk-test-secret", "base_url": "https://api.openai.com/v1"},
        format="json",
    )
    assert response.status_code == 200
    assert "sk-test-secret" not in str(response.json())
    config = AssistantSettings.load()
    assert config.api_key_encrypted != "sk-test-secret"
    assert decrypt(config.api_key_encrypted) == "sk-test-secret"


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


def test_provider_rejects_private_network_targets(monkeypatch):
    from apps.assistant.provider import _post
    from apps.common.crypto import encrypt

    config = AssistantSettings.load()
    config.api_key_encrypted = encrypt("provider-key")
    config.base_url = "https://provider.example/v1"
    monkeypatch.setattr(
        "apps.assistant.provider.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(ProviderError, match="invalid_provider_url"):
        _post("chat/completions", {}, config=config)
