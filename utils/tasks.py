from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings


@shared_task
def enviar_email_task(subject, message, html_message, recipient_list, from_email=None, anexos=None):
    send_mail(
        subject=subject,
        message=message,
        html_message=html_message,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        fail_silently=False,
    )


@shared_task(bind=True, max_retries=3)
def enviar_email_retry_task(self, subject, message, html_message, recipient_list, from_email=None, anexos=None):
    try:
        return enviar_email_task(subject, message, html_message, recipient_list, from_email, anexos)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
