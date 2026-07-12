import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from users.auth_decorators import requer_sessao_ativa
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.conf import settings

factory = RequestFactory()
request = factory.get('/financeiro/requisicoes/1/')

# Adicionar session middleware corretamente
middleware = SessionMiddleware(lambda x: x)
middleware.process_request(request)

# Configurar dados de sessão válidos
request.session['usuario_id'] = 2
request.session['usuario'] = {'papel': 'Administrador', 'nome': 'Admin', 'id': 2}
request.session['login_time'] = 1751803200.0
request.session.save()

print(f"Session key: {request.session.session_key}")
print(f"Session data: {dict(request.session)}")
print(f"Session cookie age: {settings.SESSION_COOKIE_AGE}")

# Testar decorator
@requer_sessao_ativa
def test_view(request):
    return "OK"

try:
    result = test_view(request)
    print(f"Result: {result}")
except Exception as e:
    print(f"ERRO: {e}")
    import traceback
    traceback.print_exc()
