from celery import shared_task

from utils.email_utils import _enviar_sync


@shared_task
def enviar_email_task(subject, message, html_message, recipient_list, anexos=None):
    _enviar_sync(subject, message, html_message, recipient_list, anexos)


