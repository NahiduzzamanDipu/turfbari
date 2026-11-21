from django.apps import AppConfig


class AssistantConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    verbose_name = "Website AI assistant"

    def ready(self):
        from .signals import connect_signals

        connect_signals()
        from apps.notifications.tick import EXTRA_STEPS

        from .maintenance import purge_expired_conversations, reindex_pending

        if not any(name == "assistant_knowledge" for name, _step in EXTRA_STEPS):
            EXTRA_STEPS.append(("assistant_knowledge", reindex_pending))
        if not any(name == "assistant_retention" for name, _step in EXTRA_STEPS):
            EXTRA_STEPS.append(("assistant_retention", purge_expired_conversations))
