"""Serve the built React app when Django runs without Nginx in front (e.g. PythonAnywhere).

Mirrors frontend/nginx.conf: real files in the dist folder are returned as-is, every other path
gets index.html so the React router can handle it. /assets/ should still be mapped as static files
by the host for speed; this view is the fallback.
"""

import mimetypes
from pathlib import Path

from csp.decorators import csp_exempt
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_safe


@csp_exempt()
@require_safe
def spa(request):
    dist = Path(settings.FRONTEND_DIST).resolve()
    wanted = (dist / request.path.lstrip("/")).resolve()
    if wanted.is_relative_to(dist) and wanted.is_file() and wanted.name != "index.html":
        content_type, _ = mimetypes.guess_type(wanted.name)
        response = FileResponse(wanted.open("rb"), content_type=content_type)
        if request.path.startswith("/assets/"):
            response["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
    if request.path.startswith("/assets/"):
        raise Http404
    index = dist / "index.html"
    if not index.is_file():
        raise Http404("Frontend build not found.")
    response = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
