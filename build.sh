#!/usr/bin/env bash
# Sair imediatamente se um comando falhar
set -o errexit

# Instalar as dependências do Python (apenas as necessárias para produção)
pip install -r requirements-prod.txt

# Recolher ficheiros estáticos (necessário para WhiteNoise em produção)
python manage.py collectstatic --no-input

# Aplicar migrações pendentes
python manage.py migrate --noinput
