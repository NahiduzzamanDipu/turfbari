import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class AssistantSettings(models.Model):
    """Singleton configuration. Provider credentials are Fernet-encrypted at rest."""

    PROVIDERS = [("openai_compatible", "OpenAI-compatible API")]
    default_language = models.CharField(
        max_length=2, choices=[("en", "English"), ("bn", "Bengali")], default="en"
    )
    enabled = models.BooleanField(default=True)
    display_name = models.CharField(max_length=80, default="TURFBARI AI Assistant")
    welcome_en = models.TextField(
        default="Hello! Ask me about TURFBARI features, bookings, subscriptions, SMS and account setup."
    )
    welcome_bn = models.TextField(blank=True)
    provider = models.CharField(max_length=30, choices=PROVIDERS, default="openai_compatible")
    base_url = models.URLField(max_length=300, blank=True, default="https://api.openai.com/v1")
    model = models.CharField(max_length=120, default="gpt-4o-mini")
    embedding_model = models.CharField(max_length=120, default="text-embedding-3-small")
    api_key_encrypted = models.TextField(blank=True)
    temperature = models.DecimalField(max_digits=3, decimal_places=2, default="0.20")
    max_response_tokens = models.PositiveSmallIntegerField(default=600)
    context_messages = models.PositiveSmallIntegerField(default=10)
    daily_message_limit = models.PositiveIntegerField(default=2000)
    retention_days = models.PositiveSmallIntegerField(default=30)
    input_cost_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))
    output_cost_per_million = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0"))
    last_provider_success_at = models.DateTimeField(null=True, blank=True)
    last_provider_error_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "assistant settings"

    def __str__(self):
        return "TURFBARI AI Assistant settings"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class KnowledgeArticle(BaseModel):
    SOURCE_TYPES = [
        ("article", "Help article"),
        ("url", "Website page"),
        ("upload", "Text or Markdown upload"),
    ]
    title_en = models.CharField(max_length=200)
    title_bn = models.CharField(max_length=200, blank=True)
    body_en = models.TextField()
    body_bn = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    source_type = models.CharField(max_length=12, choices=SOURCE_TYPES, default="article")
    source_url = models.URLField(max_length=1000, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.title_en


class KnowledgeSource(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        INDEXED = "indexed", "Indexed"
        FAILED = "failed", "Failed"

    key = models.CharField(max_length=160, unique=True)
    title = models.CharField(max_length=240)
    source_type = models.CharField(max_length=24, default="article")
    language = models.CharField(max_length=2, choices=[("en", "English"), ("bn", "Bengali")], default="en")
    version = models.CharField(max_length=80, blank=True)
    public_url = models.CharField(max_length=500, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["title", "language"]


class KnowledgeChunk(BaseModel):
    source = models.ForeignKey(KnowledgeSource, on_delete=models.CASCADE, related_name="chunks")
    ordinal = models.PositiveSmallIntegerField()
    text = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64)

    class Meta:
        ordering = ["source", "ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["source", "ordinal"], name="uniq_assistant_chunk_order")
        ]
        indexes = [models.Index(fields=["source", "ordinal"])]


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(max_length=64)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    language = models.CharField(max_length=2, choices=[("en", "English"), ("bn", "Bengali")], default="en")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    cleared_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return str(self.pk)


class ConversationMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "Visitor"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=Role.choices)
    client_message_id = models.UUIDField(null=True, blank=True)
    in_reply_to = models.OneToOneField(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="assistant_reply"
    )
    content = models.TextField()
    status = models.CharField(max_length=16, default="ok")
    source_ids = models.JSONField(default=list, blank=True)
    model = models.CharField(max_length=120, blank=True)
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_message_id"],
                condition=models.Q(client_message_id__isnull=False),
                name="uniq_assistant_client_message",
            )
        ]

    def __str__(self):
        return f"{self.role} message {self.pk}"


class AssistantFeedback(models.Model):
    message = models.ForeignKey(ConversationMessage, on_delete=models.CASCADE, related_name="feedback")
    helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback on message {self.message_id}: {self.helpful}"


class SuggestedQuestion(BaseModel):
    question_en = models.CharField(max_length=240)
    question_bn = models.CharField(max_length=240, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["display_order", "created_at"]


class AssistantUsageDay(models.Model):
    day = models.DateField(primary_key=True)
    message_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.day}: {self.message_count} messages"
