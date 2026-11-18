"""Startup self-test for uploaded-file storage: write, read back over the public URL, delete.

Prints one line to the deploy log so a misconfigured bucket is visible without signing in.
Never fails the start-up; uploads would show the same error to users.
"""

import urllib.request
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage, storages
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check that uploaded media can be stored, served and deleted."

    def handle(self, *args, **options):
        name = f"healthcheck/{uuid.uuid4().hex}.txt"
        backend = type(storages["default"])
        try:
            saved = default_storage.save(name, ContentFile(b"ok"))
            url = default_storage.url(saved)
            served = "n/a (local)"
            if url.startswith("http"):
                with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 (our own bucket URL)
                    served = response.status
            default_storage.delete(saved)
            self.stdout.write(f"Media storage OK: {backend.__name__}, public read {served}")
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"Media storage FAILED: {backend.__name__}: {exc!r}"))
