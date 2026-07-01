"""Configuração do APScheduler para tarefas automáticas."""
import os
from apscheduler.schedulers.background import BackgroundScheduler
from django.conf import settings
from django.core.management import call_command


def iniciar_assembleias_task():
    call_command('iniciar_assembleias')


def gerar_quotas_task():
    call_command('gerar_quotas')


def encerrar_assembleias_inativas_task():
    call_command('encerrar_assembleias_inativas')


def backup_db_task():
    call_command('backup_db')


def auto_marcar_faltas_task():
    call_command('auto_marcar_faltas')


def start_scheduler():
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
        encerrar_assembleias_inativas_task,
        'interval',
        minutes=1,
        id='encerrar_assembleias_inativas',
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
    scheduler.add_job(
        backup_db_task,
        'cron',
        hour=3,
        minute=0,
        id='backup_db_diario',
        replace_existing=True,
    )
    scheduler.add_job(
        auto_marcar_faltas_task,
        'cron',
        hour=22,
        minute=0,
        id='auto_marcar_faltas_diario',
        replace_existing=True,
        day_of_week='mon-fri',
    )
    scheduler.start()
