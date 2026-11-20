import importlib

import pytest
from django.apps import apps


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Re-create migration-seeded reference data (districts, amenities, plans).

    Transactional tests flush every table, so with --reuse-db the next run would
    otherwise start without the rows the data migrations inserted.
    """
    with django_db_blocker.unblock():
        reseed_reference_data()


def reseed_reference_data():
    for module in (
        "apps.locations.migrations.0002_seed_bangladesh",
        "apps.turfs.migrations.0002_seed_amenities",
        "apps.subscriptions.migrations.0002_seed_plans",
    ):
        importlib.import_module(module).seed(apps, None)


@pytest.fixture(autouse=True)
def _fresh_throttles():
    """Rate-limit counters live in the cache; start every test with a clean slate."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sms_outbox():
    """Test SMS go to an in-memory outbox (SMS_BACKEND=memory); start each test empty and working."""
    from apps.notifications.providers import MemoryProvider

    MemoryProvider.outbox = []
    MemoryProvider.fail_with = None
    yield
    MemoryProvider.outbox = []
    MemoryProvider.fail_with = None


@pytest.fixture(autouse=True)
def _sms_pricing(db):
    """A configured SMS price (BDT per segment), as TurfBari's admin would set in production."""
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.notifications.models import SmsPricing

    SmsPricing.objects.create(
        price_per_segment=Decimal("0.35"),
        masking_price_per_segment=Decimal("0.60"),
        bulk_price_per_segment=Decimal("0.30"),
        effective_from=timezone.now() - timedelta(days=1),
    )
