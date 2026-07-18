import logging
import sys
import traceback
from django.conf import settings
from django.template import loader
from django.http import HttpResponseServerError

logger = logging.getLogger('utils')


class ErrorCaptureMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            if settings.DEBUG:
                raise
            return self._handle_error(request)

    def _get_client_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '-')

    def _sanitize_post(self, request):
        sensitive_keys = {'password', 'senha', 'passwd', 'token', 'secret', 'csrfmiddlewaretoken'}
        data = {}
        try:
            post = request.POST
        except Exception:
            return {}
        for key in post:
            if key.lower() in sensitive_keys:
                data[key] = '***REDACTED***'
            else:
                data[key] = post[key]
        return data

    def _handle_error(self, request):
        try:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            frames = traceback.extract_tb(exc_tb)
            last = frames[-1] if frames else ('', 0, '', '')

            ip = self._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '-')[:200]
            method = request.method
            path = request.path
            query = request.META.get('QUERY_STRING', '')
            full_path = f'{path}?{query}' if query else path
            post_data = self._sanitize_post(request) if method == 'POST' else {}

            usuario_id = request.session.get('usuario_id', '-') if hasattr(request, 'session') and request.session else '-'
            tipo_usuario = request.session.get('tipo_usuario', '-') if hasattr(request, 'session') and request.session else '-'

            logger.error(
                '═══════════════════════════════════════════════════════════\n'
                'EXCEPTION: %s: %s\n'
                'Location  : %s, line %s, in %s\n'
                'Request   : %s %s\n'
                'IP        : %s\n'
                'User-Agent: %s\n'
                'Session   : usuario_id=%s tipo_usuario=%s\n'
                'POST data : %s\n'
                '═══════════════════════════════════════════════════════════\n'
                'TRACEBACK:\n%s'
                '═══════════════════════════════════════════════════════════',
                exc_type.__name__ if exc_type else 'UnknownError',
                str(exc_value) if exc_value else 'Erro desconhecido',
                last[0] if len(last) > 0 else '',
                last[1] if len(last) > 1 else 0,
                last[2] if len(last) > 2 else '',
                method, full_path,
                ip,
                user_agent,
                usuario_id,
                tipo_usuario,
                post_data,
                tb_text,
            )

            error_data = {
                'error_type': exc_type.__name__ if exc_type else 'UnknownError',
                'error_message': str(exc_value) if exc_value else 'Erro desconhecido',
                'error_file': last[0] if len(last) > 0 else '',
                'error_line': last[1] if len(last) > 1 else 0,
                'error_function': last[2] if len(last) > 2 else '',
                'traceback': tb_text,
            }
            template = loader.get_template('error_detail.html')
            content = template.render(error_data, request)
            return HttpResponseServerError(content)
        except Exception:
            try:
                content = loader.render_to_string('500.html', {}, request)
                return HttpResponseServerError(content)
            except Exception:
                return HttpResponseServerError(
                    '<html><body><h1>500 - Erro Interno</h1>'
                    '<p>Ocorreu um erro inesperado. Contacte o administrador.</p>'
                    '</body></html>',
                    content_type='text/html',
                )
