#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput 2>&1 || echo "WARN: migrate falhou (BD pode estar indisponível)"

daphne -b 0.0.0.0 -p "${PORT:-8000}" sicdoa.asgi:application
