import sys
import traceback
from django.conf import settings
from django.template import loader
from django.http import HttpResponseServerError


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

    def _handle_error(self, request):
        try:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            frames = traceback.extract_tb(exc_tb)
            last = frames[-1] if frames else ('', 0, '', '')
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
