web: python manage.py collectstatic --no-input && python manage.py migrate --noinput && daphne -b 0.0.0.0 -p $PORT sicdoa.asgi:application
worker: celery -A sicdoa worker --loglevel=info --concurrency=2
beat: celery -A sicdoa beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
