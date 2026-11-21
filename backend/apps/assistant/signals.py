import logging

from django.db import transaction

log = logging.getLogger(__name__)


def mark_stale(prefix: str):
    from .models import KnowledgeSource

    KnowledgeSource.objects.filter(key__startswith=prefix).update(status=KnowledgeSource.Status.PENDING)
    transaction.on_commit(_queue_reindex)


def _queue_reindex():
    try:
        from .tasks import reindex_knowledge

        reindex_knowledge.delay()
    except Exception:  # noqa: BLE001
        log.info("AI knowledge reindex is pending; no Celery broker is currently reachable.")


def connect_signals():
    from django.db.models.signals import post_delete, post_save

    from apps.homepage.models import HomepageFAQ
    from apps.legal.models import LegalDocumentVersion
    from apps.notifications.models import SmsPricing
    from apps.subscriptions.models import Plan

    from .models import KnowledgeArticle

    def faq_changed(sender, instance, **kwargs):
        mark_stale(f"faq:{instance.pk}:")

    def plan_changed(sender, instance, **kwargs):
        mark_stale(f"plan:{instance.pk}:")

    def legal_changed(sender, instance, **kwargs):
        mark_stale(f"legal:{instance.pk}:")

    def article_changed(sender, instance, **kwargs):
        mark_stale(f"article:{instance.pk}:")

    def sms_price_changed(sender, instance, **kwargs):
        mark_stale("sms-pricing:")

    post_save.connect(faq_changed, sender=HomepageFAQ, dispatch_uid="assistant_faq_save")
    post_delete.connect(faq_changed, sender=HomepageFAQ, dispatch_uid="assistant_faq_delete")
    post_save.connect(plan_changed, sender=Plan, dispatch_uid="assistant_plan_save")
    post_delete.connect(plan_changed, sender=Plan, dispatch_uid="assistant_plan_delete")
    post_save.connect(legal_changed, sender=LegalDocumentVersion, dispatch_uid="assistant_legal_save")
    post_save.connect(article_changed, sender=KnowledgeArticle, dispatch_uid="assistant_article_save")
    post_delete.connect(article_changed, sender=KnowledgeArticle, dispatch_uid="assistant_article_delete")
    post_save.connect(sms_price_changed, sender=SmsPricing, dispatch_uid="assistant_sms_price_save")
    post_delete.connect(sms_price_changed, sender=SmsPricing, dispatch_uid="assistant_sms_price_delete")
