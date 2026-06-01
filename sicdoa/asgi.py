import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')

django_asgi = get_asgi_application()

# ── APScheduler startup ──────────────────────────────────────────
from governanca.scheduler import start_scheduler
start_scheduler()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import governanca.routing

application = ProtocolTypeRouter({
    'http': django_asgi,
    'websocket': AuthMiddlewareStack(
        URLRouter(
            governanca.routing.websocket_urlpatterns
        )
    ),
})
