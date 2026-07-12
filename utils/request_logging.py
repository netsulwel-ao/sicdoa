"""
Middleware para logar cada requisição que entra no sistema.
Regista método, path, status code, tempo de resposta, IP e User-Agent.
"""
import logging
import re
import time

logger = logging.getLogger('utils.request_logging')

_IGNORE_PATHS = re.compile(r'^/(static/|media/|favicon\.ico|robots\.txt)')


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _IGNORE_PATHS.match(request.path):
            return self.get_response(request)

        start = time.monotonic()
        response = self.get_response(request)
        elapsed_ms = (time.monotonic() - start) * 1000

        status = response.status_code
        method = request.method
        path = request.path
        query = request.META.get('QUERY_STRING', '')
        full_path = f'{path}?{query}' if query else path

        ip = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '-')[:120]

        user_id = request.session.get('usuario_id', '-') if hasattr(request, 'session') else '-'

        if status >= 500:
            log_level = logging.ERROR
            tag = 'ERROR'
        elif status >= 400:
            log_level = logging.WARNING
            tag = 'WARN '
        elif status >= 300:
            log_level = logging.INFO
            tag = 'REDIR'
        else:
            log_level = logging.INFO
            tag = 'REQ  '

        logger.log(
            log_level,
            '[%s] %s %s %s → %s (%.0fms) | ip=%s ua=%s user=%s',
            tag,
            method.ljust(6),
            full_path,
            '',
            self._status_text(status),
            elapsed_ms,
            ip,
            user_agent,
            user_id,
        )

        return response

    @staticmethod
    def _get_client_ip(request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '-')

    @staticmethod
    def _status_text(code):
        labels = {
            200: '200 OK',
            201: '201 Created',
            204: '204 No Content',
            301: '301 Moved',
            302: '302 Redirect',
            304: '304 Not Modified',
            400: '400 Bad Request',
            401: '401 Unauthorized',
            403: '403 Forbidden',
            404: '404 Not Found',
            405: '405 Method Not Allowed',
            408: '408 Timeout',
            429: '429 Too Many Requests',
            500: '500 Internal Server Error',
            502: '502 Bad Gateway',
            503: '503 Service Unavailable',
        }
        return labels.get(code, f'{code}')
