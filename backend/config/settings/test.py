from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
AXES_ENABLED = False  # enabled explicitly in lockout tests
LOGGING = {"version": 1, "disable_existing_loggers": False}
SMS_BACKEND = "memory"
SMS_DISPATCH = "immediate"
BULKSMSBD_SENDER_ID = "TESTSENDER"
TICK_TOKEN = "test-tick-token"  # noqa: S105 - test-only value
ADMIN_EMAIL_CODE = False  # enabled explicitly in the email-code tests
