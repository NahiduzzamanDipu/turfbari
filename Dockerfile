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
RUN useradd --system --uid 10001 --home /app turfbari \
 && mkdir -p /app/staticfiles /app/media \
 && chown -R turfbari /app/staticfiles /app/media
USER turfbari

# Free tiers have no shell access, so setup runs on every start (all steps are idempotent).
CMD python manage.py migrate --noinput \
 && python manage.py createcachetable \
 && python manage.py ensure_admin \
 && python manage.py collectstatic --noinput --verbosity 0 \
 && exec gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --max-requests 500 --timeout 60 --access-logfile -
