import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo
from financeiro.views import BaseContextMixin
from django.test import RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware

# Criar request mock
factory = RequestFactory()
request = factory.get('/financeiro/requisicoes/1/')

# Adicionar session
middleware = SessionMiddleware(lambda x: x)
middleware.process_request(request)
request.session['usuario_id'] = 2
request.session['usuario'] = {'papel': 'Administrador', 'nome': 'Admin'}
request.session.save()

# Testar filtro
mixin = BaseContextMixin()
mixin.request = request

filtro = mixin._get_user_cliente_filter()
print(f"Filtro retornado: {filtro}")

# Testar query
qs = RequisicaoFundo.objects.all()
print(f"Total de requisições: {qs.count()}")

if filtro:
    qs_filtrado = qs.filter(**filtro)
    print(f"Requisições após filtro: {qs_filtrado.count()}")
    for rf in qs_filtrado:
        print(f"  - {rf.numero_requisicao}")
else:
    print("Filtro vazio (admin vê tudo)")
    for rf in qs:
        print(f"  - {rf.numero_requisicao}")
