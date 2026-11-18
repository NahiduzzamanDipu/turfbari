# TurfBari API image (Django + gunicorn). The same image runs the web server, the Celery worker
# and Celery beat; docker-compose.prod.yml picks the command.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# mysqlclient needs the MariaDB/MySQL client headers to build, and the shared lib to run.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt

COPY . .
RUN chmod +x docker-entrypoint.sh \
 && useradd --system --uid 10001 --home /app turfbari \
 && mkdir -p /app/staticfiles /app/media \
 && chown -R turfbari /app/staticfiles /app/media
USER turfbari

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
