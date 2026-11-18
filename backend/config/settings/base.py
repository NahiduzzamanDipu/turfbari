"""Settings shared by every environment. Secrets come from environment variables only."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
REPO_DIR = BASE_DIR.parent

env = environ.Env()
# Local development reads the repo-root .env; production injects real env vars.
environ.Env.read_env(REPO_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

PLATFORM_NAME = "TurfBari"
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
# Public base URL of this API for payment-gateway callbacks; blank = derive from the request.
PUBLIC_API_URL = env("PUBLIC_API_URL", default="")
# Behind our Nginx (docker-compose.prod.yml), X-Real-IP holds the real client address.
# Never enable without a proxy that overwrites the header, or clients could spoof it.
TRUST_X_REAL_IP = env.bool("TRUST_X_REAL_IP", default=False)

# ------------------------------------------------------------- subscription payments
# Accounts owners send plan fees to (shown on the subscription page; blank = method hidden).
SUBSCRIPTION_PAYMENT_ACCOUNTS = {
    "bkash": env("TURFBARI_BKASH_NUMBER", default=""),
    "nagad": env("TURFBARI_NAGAD_NUMBER", default=""),
    "rocket": env("TURFBARI_ROCKET_NUMBER", default=""),
    "bank": env("TURFBARI_BANK_DETAILS", default=""),
}
# SSLCommerz hosted checkout (cards + mobile banking). Blank = online checkout hidden.
SSLCOMMERZ_STORE_ID = env("SSLCOMMERZ_STORE_ID", default="")
SSLCOMMERZ_STORE_PASSWORD = env("SSLCOMMERZ_STORE_PASSWORD", default="")
SSLCOMMERZ_SANDBOX = env.bool("SSLCOMMERZ_SANDBOX", default=True)

# --------------------------------------------------------------------------- apps
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "axes",
    "django_celery_beat",
]
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.locations",
    "apps.turfs",
    "apps.bookings",
    "apps.applications",
    "apps.expenses",
    "apps.subscriptions",
    "apps.audit",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Must be last: lockout after repeated failed logins.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ----------------------------------------------------------------------- database
# MySQL 8 or MariaDB 10.6+ (XAMPP), InnoDB. DATABASE_URL format: mysql://user:password@host:3306/dbname
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"].update(
    {
        "ATOMIC_REQUESTS": False,
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "charset": "utf8mb4",  # full Unicode incl. Bangla and emoji
            # Strict mode: reject truncated/invalid data instead of silently altering it.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,"
            "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'",
            # READ COMMITTED + SELECT ... FOR UPDATE row locks guard booking overlaps.
            "isolation_level": "read committed",
            # Options from the URL query, e.g. ?ssl_mode=REQUIRED for hosted MySQL (Aiven, TiDB).
            **DATABASES["default"].get("OPTIONS", {}),
        },
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
    }
)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------------------------------------------------- cache
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
# Redis cache when CACHE_URL is set; otherwise a per-process memory cache (fine for local dev,
# not for multi-worker production — prod must set CACHE_URL so throttles are shared).
_cache_url = env("CACHE_URL", default="")
# CACHE_URL=db://<table> uses a shared MySQL table instead (hosts without Redis; run createcachetable).
if _cache_url.startswith("db://"):
    _cache = {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": _cache_url[5:]}
elif _cache_url:
    _cache = {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _cache_url}
else:
    _cache = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
CACHES = {"default": _cache | {"KEY_PREFIX": "turfbari"}}

# --------------------------------------------------------------- authentication
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.EmailOrUsernameBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_RESET_TIMEOUT = 60 * 60  # 1 hour

SESSION_COOKIE_NAME = "turfbari_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14  # "remember me" length; short sessions expire on browser close
CSRF_COOKIE_NAME = "turfbari_csrftoken"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # SPA reads it to send X-CSRFToken

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

# ---------------------------------------------------------------- localization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------- static / media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Single-host deploys (no Nginx in front): Django serves the built React app from this folder.
FRONTEND_DIST = env("FRONTEND_DIST", default="")
# ...and serves /static/ and uploaded /media/ itself (low-traffic hosts only).
SERVE_MEDIA = env.bool("SERVE_MEDIA", default=False)
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

# --------------------------------------------------------------------- DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "600/min",
        "login": "10/min",
        "two_factor": "10/min",
        "public_booking": "5/min",
        "public_application": "3/hour",
    },
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "TurfBari API",
    "DESCRIPTION": "Smart Turf Management System — public, admin and workspace APIs.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------- Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Synced into django-celery-beat's tables when beat starts (editable later in Django admin).
CELERY_BEAT_SCHEDULE = {
    "plan-expiry-reminders": {
        "task": "subscriptions.send_expiry_reminders",
        "schedule": crontab(hour=9, minute=0),  # 9 AM Asia/Dhaka, daily
    },
}

# ----------------------------------------------------------------------- email
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=1025)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="TurfBari <no-reply@turfbari.com>")

# ---------------------------------------------------------------------- security
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "script-src": ["'self'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
    }
}

# ----------------------------------------------------------------------- logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
