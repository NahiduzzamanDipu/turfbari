import importlib

import pytest
from django.apps import apps


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Re-create migration-seeded reference data (districts, amenities).

    Transactional tests flush every table, so with --reuse-db the next run would
    otherwise start without the rows the data migrations inserted.
    """
    with django_db_blocker.unblock():
        for module in (
            "apps.locations.migrations.0002_seed_bangladesh",
            "apps.turfs.migrations.0002_seed_amenities",
        ):
            importlib.import_module(module).seed(apps, None)
