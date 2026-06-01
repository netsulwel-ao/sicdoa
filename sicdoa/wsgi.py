"""
WSGI config for sicdoa project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os
import django
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')

# ── Static files: ensure STATIC_ROOT exists without separate build step ──
django.setup()
from django.conf import settings
from django.core.management import call_command
static_root = settings.STATIC_ROOT
if static_root and not os.path.isdir(static_root):
    os.makedirs(static_root, exist_ok=True)
    call_command('collectstatic', '--no-input', verbosity=0)

application = get_wsgi_application()

# ── APScheduler startup ──────────────────────────────────────────
from governanca.scheduler import start_scheduler
start_scheduler()
