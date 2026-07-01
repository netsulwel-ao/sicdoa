import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Segurança
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise RuntimeError('SECRET_KEY environment variable is required')

DEBUG = True
ALLOWED_HOSTS = ['*']

# ── Redis (cache + channel layer + Celery broker) ─────────────────────
REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
REDIS_ENABLED = os.environ.get('REDIS_ENABLED', '0') == '1'

# Aplicações
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'utils',
    'users',
    'aduaneiro',
    'rh',
    'clientes',
    'governanca',
    'financeiro',
    'channels',
    'django_apscheduler',
]

if REDIS_ENABLED:
    INSTALLED_APPS += ['django_celery_beat']

MIDDLEWARE = [
    'utils.middleware.ErrorCaptureMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'users.middleware.SessionExpirationMiddleware',
    'users.middleware.ActivityLogMiddleware',
]

ROOT_URLCONF = 'sicdoa.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': False,
        'OPTIONS': {
            'builtins': ['rh.templatetags.rh_extras'],
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'rh.context_processors.cargos_mesa',
                'users.context_processors.user_permissoes',
            ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ],
        },
    },
]

WSGI_APPLICATION = 'sicdoa.wsgi.application'
ASGI_APPLICATION = 'sicdoa.asgi.application'

# ── CACHE (Redis via django-redis) ────────────────────────────────────
if REDIS_ENABLED:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_CLASS': 'redis.BlockingConnectionPool',
                'CONNECTION_POOL_CLASS_KWARGS': {'max_connections': 50, 'timeout': 20},
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
            },
            'KEY_PREFIX': 'sicdoa',
            'TIMEOUT': 300,
        },
        'stats': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': os.environ.get('REDIS_URL_STATS', 'redis://127.0.0.1:6379/1'),
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_CLASS_KWARGS': {'max_connections': 10, 'timeout': 10},
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
            },
            'KEY_PREFIX': 'sicdoa_stats',
            'TIMEOUT': 600,
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'sicdoa-cache',
            'TIMEOUT': 300,
        },
    }

# ── Channel Layer (Redis para WebSocket entre workers) ────────────────
if REDIS_ENABLED:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [os.environ.get('REDIS_URL_CHANNELS', 'redis://127.0.0.1:6379/2')],
                'capacity': 1500,
                'expiry': 60,
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

IS_PRODUCTION = os.environ.get('ENVIRONMENT', '').lower() == 'production'
if IS_PRODUCTION:
    DEBUG = False
    ALLOWED_HOSTS = [
        host.strip()
        for host in os.environ.get('ALLOWED_HOSTS', '*').split(',')
        if host.strip()
    ]
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
        if origin.strip()
    ]
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ── MySQL com Connection Pooling ──────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'sicdoav1'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'connect_timeout': 10,
            'charset': 'utf8mb4',
        },
        'CONN_MAX_AGE': 300,
    }
}

# Validação de passwords
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Backends de autenticação (ordem: primeiro custom, depois Django admin padrão)
AUTHENTICATION_BACKENDS = [
    'users.auth_backends.UsuarioBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# URLs de Autenticação
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Internacionalização
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'Africa/Luanda'
USE_I18N = True
USE_TZ = True

# Ficheiros estáticos
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Media
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Sessão — Redis cache (ou signed_cookies se Redis não disponível)
if REDIS_ENABLED:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_AGE = 3600  # 1 hora
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_SAVE_EVERY_REQUEST = False

# Email
EMAIL_BACKEND = 'utils.email_backend.SSLRelaxedEmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', os.environ.get('EMAIL_PASS', ''))
DEFAULT_FROM_EMAIL = f'{os.environ.get("EMAIL_FROM_NAME", "SICDOA")} <{os.environ.get("EMAIL_FROM_ADDRESS", EMAIL_HOST_USER)}>'
EMAIL_SUBJECT_PREFIX = '[SICDOA] '
EMAIL_TIMEOUT = 30

# URL pública do sistema (usada em emails — credenciais, convites, etc.)
SITE_URL = os.environ.get('SITE_URL', 'https://sicdoa.cdoangola.co.ao').rstrip('/')

# LiveKit — videoconferência para plenário virtual
LIVEKIT_URL = os.environ.get('LIVEKIT_URL', '')
LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY', '')
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET', '')

# ── Celery (tarefas assíncronas) ───────────────────────────────────
if REDIS_ENABLED:
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', REDIS_URL)
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', REDIS_URL)
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 300
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# ── Backup ─────────────────────────────────────────────────────────
BACKUP_DIR = os.environ.get('BACKUP_DIR', os.path.join(BASE_DIR, 'backups'))
BACKUP_RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', '30'))
BACKUP_EMAIL_TO = os.environ.get('BACKUP_EMAIL_TO', 'ramosfranciscotch@gmail.com')
ERROR_REPORT_EMAIL = os.environ.get('ERROR_REPORT_EMAIL', BACKUP_EMAIL_TO)

# ── APScheduler (tarefas agendadas) ────────────────────────────────
APSCHEDULER_DATETIME_FORMAT = 'N/A'
APSCHEDULER_RUN_NOW_TIMEOUT = 25
SCHEDULER_CONFIG = {
    'apscheduler.jobstores.default': {
        'type': 'sqlalchemy',
        'url': f'sqlite:///{BASE_DIR / "apscheduler.db"}',
    },
    'apscheduler.executors.default': {
        'class': 'apscheduler.executors.pool:ThreadPoolExecutor',
        'max_workers': 1,
    },
    'apscheduler.job_defaults.coalesce': True,
    'apscheduler.job_defaults.max_instances': 1,
    'apscheduler.timezone': 'UTC',
}

# ── Logging (única definição) ──────────────────────────────────────
import logging
logging.getLogger('apscheduler').setLevel(logging.WARNING)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if DEBUG else 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'apscheduler': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'governanca': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}

# ── Startup warnings ───────────────────────────────────────────────────
import logging
_logger = logging.getLogger(__name__)
if IS_PRODUCTION and not REDIS_ENABLED:
    _logger.warning(
        'REDIS_ENABLED=0 em produção — WebSocket pode falhar com múltiplos workers. '
        'Define REDIS_ENABLED=1 no Render dashboard e adiciona um Redis service.'
    )