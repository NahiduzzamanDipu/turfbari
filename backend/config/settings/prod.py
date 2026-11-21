from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

if not env("CACHE_URL", default=""):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("CACHE_URL (Redis) is required in production for shared rate limits.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# Render may probe the container over HTTP before its proxy terminates external TLS.
# Keep the minimal liveness endpoint reachable without redirecting health checks.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False  # opt in once the domain is stable

if TRUST_X_REAL_IP:  # noqa: F405
    # Login lockouts (django-axes) key on the client IP too.
    AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_REAL_IP", "REMOTE_ADDR")

# Object storage for uploaded media (S3-compatible: Cloudflare R2, DigitalOcean Spaces, AWS S3).
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="") or None
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="") or None
if AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
    }
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    # Supabase Storage / MinIO need path-style URLs; public files are served from a different
    # base than the S3 API, e.g. <ref>.supabase.co/storage/v1/object/public/<bucket>.
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="auto")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="") or None

SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, send_default_pii=False, traces_sample_rate=0.05)
