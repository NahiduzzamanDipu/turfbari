from celery import shared_task


@shared_task(name="assistant.reindex_knowledge")
def reindex_knowledge():
    from .knowledge import sync_knowledge

    return sync_knowledge()
