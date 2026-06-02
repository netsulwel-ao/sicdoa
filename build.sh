#!/usr/bin/env bash
set -o errexit

pip install -r requirements-prod.txt

python manage.py collectstatic --no-input
