from celery import shared_task

from .tick import run_tick


@shared_task(name="notifications.tick")
def tick_task() -> dict:
    return run_tick()
