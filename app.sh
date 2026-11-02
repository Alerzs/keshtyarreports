#!/bin/sh
set -eu

cd "$(dirname "$0")"

if command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi

"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput
"$PY" manage.py ensure_admin

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 \
  --timeout 120
