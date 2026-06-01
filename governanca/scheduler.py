"""Configuração do APScheduler para tarefas automáticas."""
import os
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command


def iniciar_assembleias_task():
    """Task que inicia assembleias cuja data/hora já passou."""
    call_command('iniciar_assembleias')


def gerar_quotas_task():
    """Task que gera quotas automaticamente no dia 1 de cada mês."""
    call_command('gerar_quotas')


def start_scheduler():
    """Inicia o scheduler em background (chamado pelo ASGI/WSGI)."""
    if os.environ.get('RUN_MAIN') != 'true' and 'RUN_MAIN' in os.environ and settings.DEBUG:
        return
    if hasattr(start_scheduler, '_scheduler_started'):
        return
    start_scheduler._scheduler_started = True

    scheduler = BackgroundScheduler(settings.SCHEDULER_CONFIG)
    scheduler.add_job(
        iniciar_assembleias_task,
        'interval',
        minutes=1,
        id='iniciar_assembleias',
        replace_existing=True,
    )
    scheduler.add_job(
        gerar_quotas_task,
        'cron',
        day=1,
        hour=0,
        minute=0,
        id='gerar_quotas_mensal',
        replace_existing=True,
    )
    scheduler.start()
