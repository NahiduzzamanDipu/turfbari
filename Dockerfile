# Single-service TurfBari image for free hosts such as Render: builds the React app, then runs
# Django (gunicorn), which serves the API, the built site and uploaded media in one process.
# The multi-container setup for a VPS is docker-compose.prod.yml.
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    FRONTEND_DIST=/app/frontend-dist \
    SERVE_MEDIA=true \
    PORT=8000

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements/ requirements/
RUN pip install -r requirements/prod.txt
COPY backend/ .
COPY --from=frontend /app/dist /app/frontend-dist
# Static files are collected at build time (not on every start). The values below are build-only
# placeholders; the real ones come from the host's environment at run time.
RUN DJANGO_SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.sqlite3 CACHE_URL=db://build \
    AWS_STORAGE_BUCKET_NAME=build-only python manage.py collectstatic --noinput --verbosity 0 \
 && useradd --system --uid 10001 --home /app turfbari \
 && mkdir -p /app/media \
 && chown -R turfbari /app/media
USER turfbari

# Free tiers have no shell access, so setup runs on every start. `startup` does migrate, cache table
# and admin check in one Python process (each extra manage.py call costs seconds on a small CPU);
# the media-storage self-test runs in the background so it doesn't delay the first request.
# One worker with threads boots faster and uses less memory than several worker processes.
CMD python manage.py startup \
 && (python manage.py check_media_storage &) \
 && exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 \
    --max-requests 1000 --max-requests-jitter 100 --timeout 60 --access-logfile -
