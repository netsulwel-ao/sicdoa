#!/usr/bin/env python
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo
from financeiro.views import requisicao_pdf
from django.test import RequestFactory
from django.contrib.auth.models import User

# Criar uma requisição fake
factory = RequestFactory()
request = factory.get('/fake/')
request.session = {'usuario': {'papel': 'Administrador'}}

# Obter uma requisição real do banco
requisicao = RequisicaoFundo.objects.first()

if requisicao:
    print(f"Testando requisição: {requisicao.numero_requisicao}")
    try:
        # Chamar a função PDF
        response = requisicao_pdf(request, requisicao.pk)
        pdf_content = response.content
        print(f"✓ PDF gerado com sucesso!")
        print(f"✓ Tamanho do PDF: {len(pdf_content)} bytes")
        
        # Salvar arquivo para inspecção
        with open('C:\\projetos\\sicdoa\\test_requisicao.pdf', 'wb') as f:
            f.write(pdf_content)
        print(f"✓ Arquivo salvo em: C:\\projetos\\sicdoa\\test_requisicao.pdf")
        
    except Exception as e:
        print(f"✗ Erro ao gerar PDF: {e}")
        import traceback
        traceback.print_exc()
else:
    print("✗ Nenhuma requisição encontrada")
