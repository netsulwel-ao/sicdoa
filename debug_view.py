import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from django.test import RequestFactory
from financeiro.views import RequisicaoFundoDetailView
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

factory = RequestFactory()
request = factory.get('/financeiro/requisicoes/1/')

# Adicionar session
middleware = SessionMiddleware(lambda x: x)
middleware.process_request(request)
request.session['usuario_id'] = 2
request.session['usuario'] = {'papel': 'Administrador', 'nome': 'Admin'}
request.session['login_time'] = timezone.now().isoformat()
request.session.save()

# Adicionar user Django
request.user = AnonymousUser()

# Testar view
view = RequisicaoFundoDetailView.as_view()
try:
    response = view(request, pk=1)
    print(f"Status code: {response.status_code}")
    print(f"Content-Type: {response.get('Content-Type')}")
    
    # Se for TemplateResponse, renderizar
    if hasattr(response, 'render'):
        response.render()
    
    print(f"Content length: {len(response.content)}")
    
    # Se foi renderizado, tentar detectar o problema
    if response.status_code == 200:
        content = response.content.decode('utf-8', errors='ignore')
        print(f"\nPrimeiros 1000 caracteres:")
        print(content[:1000])
        
        if 'RF-2026/001' in content:
            print("\n✓ Requisição encontrada no HTML")
        else:
            print("\n✗ Requisição NÃO encontrada no HTML")
            
        if 'Nunes Memba' in content:
            print("✓ Cliente encontrado no HTML")
        else:
            print("✗ Cliente NÃO encontrado no HTML")
            
        if 'error' in content.lower():
            print("✗ Encontrado 'error' no HTML")
except Exception as e:
    print(f"ERRO ao chamar view: {e}")
    import traceback
    traceback.print_exc()
