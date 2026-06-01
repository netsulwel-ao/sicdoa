import os

if os.environ.get('REDIS_ENABLED', '0') == '1':
    try:
        from .celery import app as celery_app
        __all__ = ('celery_app',)
    except ImportError:
        pass
