#!/usr/bin/env python
"""
Script para limpar todas as sessões antigas do sistema.
Execute este script e depois faça login novamente.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sicdoa.settings')
django.setup()

from django.contrib.sessions.models import Session

# Contar sessões antes
total_antes = Session.objects.count()
print(f"Sessões antes: {total_antes}")

# Deletar todas as sessões
Session.objects.all().delete()

# Contar sessões depois
total_depois = Session.objects.count()
print(f"Sessões depois: {total_depois}")
print(f"Sessões removidas: {total_antes - total_depois}")
print("\n✅ Todas as sessões foram limpas!")
print("👉 Faça login novamente no navegador para criar uma nova sessão.")
