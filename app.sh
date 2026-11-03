#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py ensure_admin

PORT="${PORT:-8000}"
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
