#!/bin/sh
# Web container only: apply migrations and collect static files before starting gunicorn.
# Worker / beat containers set RUN_MIGRATIONS=0 so only one container migrates.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput --verbosity 0
fi

exec "$@"
