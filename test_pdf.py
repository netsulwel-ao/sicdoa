#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from financeiro.models import RequisicaoFundo
from datetime import datetime

# Obter uma requisição do banco de dados
requisicao = RequisicaoFundo.objects.first()

if requisicao:
    print(f"✓ Encontrada Requisição: {requisicao.numero_requisicao}")
    print(f"✓ Banca: {requisicao.banca}")
    print(f"✓ Cliente: {requisicao.cliente}")
    print(f"✓ Data: {requisicao.data_emissao}")
    print(f"✓ Total: {requisicao.total_geral}")
    print(f"✓ Linhas: {requisicao.linhas.count()}")
    
    # Verificar linhas
    for linha in requisicao.linhas.all():
        print(f"  - {linha.tipo_custo}: {linha.valor} (Documentada: {linha.documentada})")
    
    print("\n✓ Teste de estrutura completado com sucesso!")
else:
    print("✗ Nenhuma Requisição encontrada no banco de dados")
