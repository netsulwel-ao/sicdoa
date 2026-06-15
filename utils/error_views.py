import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from utils.email_utils import _enviar_sync

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def report_error_view(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'message': 'JSON inválido'}, status=400)

    error_type = data.get('type', 'Desconhecido')
    error_message = data.get('message', '')
    error_file = data.get('file', '')
    error_line = data.get('line', '')
    error_function = data.get('function', '')
    traceback_text = data.get('traceback', '')
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    remote_ip = request.META.get('REMOTE_ADDR', '')

    assunto = f'[ERRO] {error_type}: {error_message[:120]}'
    site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')

    texto = f"""
ERRO REPORTADO — SICDOA
{'='*60}

Tipo:     {error_type}
Mensagem: {error_message}
Ficheiro: {error_file}
Linha:    {error_line}
Função:   {error_function}
IP:       {remote_ip}
User-Agent: {user_agent}
Origem:   {site_url}

TRACEBACK:
{'-'*60}
{traceback_text}
{'='*60}
"""

    destinatario = getattr(settings, 'ERROR_REPORT_EMAIL', None) or getattr(settings, 'BACKUP_EMAIL_TO', '')
    if not destinatario:
        logger.warning("Nenhum destinatário configurado para reporte de erros (ERROR_REPORT_EMAIL)")
        return JsonResponse({'success': False, 'message': 'Email de reporte não configurado'}, status=500)

    try:
        _enviar_sync(assunto, texto, None, destinatario)
        logger.info("Erro reportado para %s: %s", destinatario, assunto)
        return JsonResponse({'success': True, 'message': 'Erro reportado com sucesso'})
    except Exception as e:
        logger.error("Falha ao enviar reporte de erro: %s", str(e))
        return JsonResponse({'success': False, 'message': f'Falha ao enviar email: {str(e)}'}, status=500)
