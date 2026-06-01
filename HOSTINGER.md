# Instruções para Hospedar o SICDOA na Hostinger (VPS Ubuntu 24.04)

## 1. Acessar a VPS via SSH

```bash
ssh root@31.97.155.96
```

## 2. Atualizar o sistema

```bash
apt update && apt upgrade -y
```

## 3. Instalar dependências do sistema

> **Nota:** No Ubuntu 24.04, o Python 3.11 não está nos repositórios padrão. É necessário adicionar o PPA `deadsnakes`.

```bash
apt install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt update
apt install -y python3.11 python3.11-venv python3.11-dev mysql-server redis-server nginx
apt install -y build-essential libssl-dev libffi-dev pkg-config
apt install -y libmysqlclient-dev libxml2-dev libxslt1-dev
```

Caso prefira usar o Python 3.12 (já incluído no Ubuntu 24.04):

```bash
apt install -y python3.12 python3.12-venv python3.12-dev mysql-server redis-server nginx
apt install -y build-essential libssl-dev libffi-dev pkg-config
apt install -y libmysqlclient-dev libxml2-dev libxslt1-dev
```

## 4. Configurar MySQL

O MySQL 8.0 no Ubuntu 24.04 usa `auth_socket` para o root por padrão. Use `sudo mysql` para entrar.

```bash
mysql_secure_installation
```

Durante o `mysql_secure_installation`:
- Escolha `y` para o componente de validação de passwords
- Escolha `0` (LOW) para a política
- A password do root será saltada (fica com `auth_socket`)
- Responda `y` para remover utilizadores anónimos
- Responda `y` para desativar login remoto do root
- Responda `y` para remover base de dados de teste
- Responda `y` para recarregar privilégios

```bash
sudo mysql -u root
```

```sql
CREATE DATABASE sicdoav1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'sicdoa_user'@'localhost' IDENTIFIED BY 'SUA_SENHA_FORTE';
GRANT ALL PRIVILEGES ON sicdoav1.* TO 'sicdoa_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## 5. Configurar Redis

```bash
apt install -y redis-server
systemctl enable --now redis-server
redis-cli ping  # deve responder PONG
```

## 6. Clonar o projeto

```bash
mkdir -p /var/www
cd /var/www
git clone https://github.com/netsulwel-ao/sicdoa.git sicdoa
```

## 7. Criar ambiente virtual e instalar dependências

> **Importante:** No Ubuntu 24.04, `python3` aponta para Python 3.12, mas o projeto requer Python 3.11. Use **sempre** `python3.11` para criar a venv. Após criar, verifique a versão com `python --version`.

```bash
cd /var/www/sicdoa
python3.11 -m venv venv
source venv/bin/activate
python --version  # Deve mostrar Python 3.11.x
pip install --upgrade pip
pip install -r requirements-prod.txt
```

Se aparecer `Python 3.12.x`, a venv foi criada com o Python errado. Refaça:

```bash
deactivate
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
python --version  # Confirmar 3.11
pip install --upgrade pip
pip install -r requirements-prod.txt
```

## 8. Configurar variáveis de ambiente

Crie o arquivo `/var/www/sicdoa/.env`:

```env
SECRET_KEY=gerar_uma_chave_segura
ENVIRONMENT=production
DEBUG=False
ALLOWED_HOSTS=seu-dominio.com,www.seu-dominio.com,31.97.155.96
CSRF_TRUSTED_ORIGINS=https://seu-dominio.com,https://www.seu-dominio.com
SITE_URL=https://seu-dominio.com

DB_NAME=sicdoav1
DB_USER=sicdoa_user
DB_PASSWORD=SUA_SENHA_FORTE
DB_HOST=localhost
DB_PORT=3306

REDIS_ENABLED=1
REDIS_URL=redis://localhost:6379/0
REDIS_URL_STATS=redis://localhost:6379/1
REDIS_URL_CHANNELS=redis://localhost:6379/2

EMAIL_HOST_USER=amanhademanda65@gmail.com
EMAIL_HOST_PASSWORD=senha_de_app_do_gmail

LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
```

Para gerar uma SECRET_KEY segura:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 9. Rodar migrações e coletar estáticos

```bash
cd /var/www/sicdoa
source venv/bin/activate
python --version  # Confirmar 3.11 antes de continuar
python manage.py migrate --noinput
python manage.py collectstatic --no-input
```

## 10. Configurar systemd services

### `/etc/systemd/system/sicdoa-daphne.service`

```ini
[Unit]
Description=SICDOA Daphne ASGI
After=network.target mysql.service redis-server.service

[Service]
User=root
WorkingDirectory=/var/www/sicdoa
ExecStart=/var/www/sicdoa/venv/bin/daphne -b 127.0.0.1 -p 8000 sicdoa.asgi:application
Restart=always
RestartSec=5
EnvironmentFile=/var/www/sicdoa/.env

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/sicdoa-celery-worker.service`

```ini
[Unit]
Description=SICDOA Celery Worker
After=network.target redis-server.service

[Service]
User=root
WorkingDirectory=/var/www/sicdoa
ExecStart=/var/www/sicdoa/venv/bin/celery -A sicdoa worker --loglevel=info --concurrency=2
Restart=always
RestartSec=5
EnvironmentFile=/var/www/sicdoa/.env

[Install]
WantedBy=multi-user.target
```

### `/etc/systemd/system/sicdoa-celery-beat.service`

```ini
[Unit]
Description=SICDOA Celery Beat
After=network.target redis-server.service

[Service]
User=root
WorkingDirectory=/var/www/sicdoa
ExecStart=/var/www/sicdoa/venv/bin/celery -A sicdoa beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=always
RestartSec=5
EnvironmentFile=/var/www/sicdoa/.env

[Install]
WantedBy=multi-user.target
```

### Ativar todos os services

```bash
systemctl daemon-reload
systemctl enable --now sicdoa-daphne
systemctl enable --now sicdoa-celery-worker
systemctl enable --now sicdoa-celery-beat
```

## 11. Configurar Nginx como proxy reverso

### `/etc/nginx/sites-available/sicdoa`

```nginx
server {
    listen 80;
    server_name seu-dominio.com www.seu-dominio.com;

    location /static/ {
        alias /var/www/sicdoa/staticfiles/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/sicdoa/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

### Ativar site e configurar SSL

```bash
ln -s /etc/nginx/sites-available/sicdoa /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Instalar SSL com Let's Encrypt
apt install -y certbot python3-certbot-nginx
certbot --nginx -d seu-dominio.com -d www.seu-dominio.com
```

## 12. Firewall (se ativo)

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

## 13. Verificar logs

```bash
journalctl -u sicdoa-daphne -f
journalctl -u sicdoa-celery-worker -f
journalctl -u sicdoa-celery-beat -f
```

## Observações importantes

- **Redis é obrigatório** em produção (WebSockets + Celery + cache)
- O MySQL precisa estar rodando antes do Daphne
- Os arquivos `~WRL4012.tmp` e `Untitled` contêm credenciais Gmail — **remova-os do servidor** e use senha de app do Gmail
- O `apscheduler.db` será recriado automaticamente após o migrate
- Se for usar LiveKit, configure um servidor LiveKit separado e preencha as variáveis `LIVEKIT_*`
- Para entrar no MySQL como root use `sudo mysql -u root` (devido ao `auth_socket`)
- Sempre active o ambiente virtual com `source venv/bin/activate` antes de comandos Python/Django
