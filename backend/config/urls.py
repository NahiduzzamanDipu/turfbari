from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.common.permissions import IsPlatformAdmin

urlpatterns = [
    # Django's built-in admin is kept for emergency data repair only, at a non-obvious path.
    path("django-admin/", admin.site.urls),
    path("api/", include("apps.common.urls")),
    path("api/", include("config.api_urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[IsPlatformAdmin] if not settings.DEBUG else []),
        name="api-schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema", permission_classes=[IsPlatformAdmin] if not settings.DEBUG else []
        ),
        name="api-docs",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.SERVE_MEDIA and not settings.DEBUG:
    from django.views.static import serve

    urlpatterns += [
        # Uploads are re-encoded images; never serve anything else from MEDIA_ROOT.
        re_path(
            r"^media/(?P<path>.+\.(?:webp|png|jpe?g))$", serve, {"document_root": settings.MEDIA_ROOT}
        ),
        re_path(r"^static/(?P<path>.+)$", serve, {"document_root": settings.STATIC_ROOT}),
    ]

if settings.FRONTEND_DIST:
    from config.spa import spa

    # Must stay last: every path the API doesn't own belongs to the React router.
    urlpatterns += [re_path(r"^(?!api/|django-admin/|media/|static/).*$", spa)]
