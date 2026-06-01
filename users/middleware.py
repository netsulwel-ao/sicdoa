"""
Middleware para verificar automaticamente a expiração da sessão.
"""
from django.shortcuts import redirect
from django.utils import timezone
from .auth_decorators import sessao_expirada, limpar_sessao


class SessionExpirationMiddleware:
    """
    Middleware que verifica se a sessão expirou e redireciona para login.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import logging
        logger = logging.getLogger(__name__)
        
        # Não verificar sessão para páginas públicas
        public_paths = ['/login/', '/logout/', '/static/', '/media/', '/admin/']
        
        # Verificar se o path é público
        if any(request.path.startswith(path) for path in public_paths):
            return self.get_response(request)
        
        # Debug: log da sessão
        logger.info(f"Middleware - Path: {request.path}")
        logger.info(f"Middleware - Session ID: {request.COOKIES.get('sessionid', 'NONE')}")
        logger.info(f"Middleware - usuario_id: {request.session.get('usuario_id')}")
        
        # Verificar se há sessão ativa
        if request.session.get('usuario_id'):
            # Verificar se a sessão expirou
            if sessao_expirada(request):
                logger.warning(f"Middleware - Sessão expirada, limpando...")
                limpar_sessao(request)
                # Se for requisição AJAX, retornar JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({
                        'error': 'Sessão expirada',
                        'redirect': '/login/'
                    }, status=401)
                # Se for requisição normal, redirecionar
                return redirect('login')
        
        response = self.get_response(request)
        return response
