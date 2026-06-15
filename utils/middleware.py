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
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        frames = traceback.extract_tb(exc_tb)
        last = frames[-1] if frames else ('', 0, '', '')
        error_data = {
            'error_type': exc_type.__name__,
            'error_message': str(exc_value),
            'error_file': last[0],
            'error_line': last[1],
            'error_function': last[2],
            'traceback': tb_text,
        }
        template = loader.get_template('error_detail.html')
        content = template.render(error_data)
        return HttpResponseServerError(content)
