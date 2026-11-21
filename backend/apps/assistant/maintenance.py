from datetime import timedelta

from django.utils import timezone


def reindex_pending():
    from .knowledge import sync_knowledge
    from .models import AssistantSettings, KnowledgeSource

    if not AssistantSettings.load().enabled:
        return {"skipped": "assistant disabled"}
    pending = KnowledgeSource.objects.filter(status=KnowledgeSource.Status.PENDING).exists()
    if not KnowledgeSource.objects.exists():
        pending = True
    if not pending:
        return {"pending": 0}
    return sync_knowledge()


def purge_expired_conversations():
    from .models import AssistantSettings, AssistantUsageDay, Conversation

    cutoff = timezone.now() - timedelta(days=AssistantSettings.load().retention_days)
    deleted, _ = Conversation.objects.filter(updated_at__lt=cutoff).delete()
    old_usage, _ = AssistantUsageDay.objects.filter(
        day__lt=timezone.localdate() - timedelta(days=90)
    ).delete()
    return {"conversations_and_messages_deleted": deleted, "usage_days_deleted": old_usage}
