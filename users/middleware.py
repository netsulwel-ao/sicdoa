"""
Middleware para verificar automaticamente a expiração da sessão e registar logs de atividade.
"""
import re
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
        # Não verificar sessão para páginas públicas
        public_paths = ['/login/', '/logout/', '/static/', '/media/', '/admin/']
        
        # Verificar se o path é público
        if any(request.path.startswith(path) for path in public_paths):
            return self.get_response(request)
        
        # Verificar se há sessão ativa
        if request.session.get('usuario_id'):
            # Verificar se a sessão expirou
            if sessao_expirada(request):
                from .models import registrar_log
                registrar_log(request, 'SESSAO_EXPIRADA', 'users',
                              f"Sessão expirada para o utilizador")
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

            # Verificar se o utilizador ainda está ativo
            if request.session.get('tipo_usuario') == 'usuario':
                from .models import Usuario
                try:
                    u = Usuario.objects.get(pk=request.session['usuario_id'])
                    if u.status != 'Ativo':
                        from .models import registrar_log
                        registrar_log(request, 'LOGOUT', 'users',
                                      f"Sessão terminada — conta {u.status.lower()}: {u.email}")
                        limpar_sessao(request)
                        from django.contrib import messages
                        messages.error(
                            request,
                            "A sua conta encontra-se " + u.status.lower() + ". Entre em contacto com o seu responsável."
                        )
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            from django.http import JsonResponse
                            return JsonResponse({
                                'error': 'Conta ' + u.status.lower(),
                                'redirect': '/login/'
                            }, status=401)
                        return redirect('login')
                    # Verificar se Colaborador Institucional perdeu a função
                    if u.papel == 'Colaborador Institucional' and not u.funcao_id:
                        from .models import registrar_log
                        registrar_log(request, 'LOGOUT', 'users',
                                      f"Sessão terminada — colaborador sem função: {u.email}")
                        limpar_sessao(request)
                        from django.contrib import messages
                        messages.error(
                            request,
                            "A sua função foi removida. Contacte o administrador para lhe ser atribuída uma nova função."
                        )
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            from django.http import JsonResponse
                            return JsonResponse({
                                'error': 'Função removida',
                                'redirect': '/login/'
                            }, status=401)
                        return redirect('login')
                except Usuario.DoesNotExist:
                    pass
        
        response = self.get_response(request)
        return response


# URLs que não devem ser logadas (estáticas, health checks, etc.)
_IGNORAR_URLS = re.compile(r'^/(static/|media/|favicon\.ico|robots\.txt|extend-session/)')

# Mapeamento de prefixos de URL para módulos
_URL_MODULO_MAP = {
    '/financeiro/': 'financeiro',
    '/clientes/': 'clientes',
    '/rh/': 'rh',
    '/governanca/': 'governanca',
    '/aduaneiro/': 'aduaneiro',
    '/users/': 'users',
    '/login': 'users',
    '/logout': 'users',
}


class ActivityLogMiddleware:
    """
    Middleware que regista automaticamente as acções dos utilizadores no LogAtividade.
    Regista VIEW em páginas GET e acções específicas em POST.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if _IGNORAR_URLS.match(path):
            return self.get_response(request)

        # Não logar páginas públicas de login (o login_view já faz logging manual)
        if path in ('/', '/login/', '/login-portal/'):
            return self.get_response(request)

        if not request.session.get('usuario_id'):
            return self.get_response(request)

        self._determinar_modulo(request)
        self._registar_acesso(request)

        response = self.get_response(request)
        return response

    def _determinar_modulo(self, request):
        path = request.path
        for prefixo, modulo in _URL_MODULO_MAP.items():
            if path.startswith(prefixo):
                request._log_modulo = modulo
                return
        request._log_modulo = 'sistema'

    def _registar_acesso(self, request):
        from .models import registrar_log
        path = request.path
        metodo = request.method

        # Só regista VIEW em GET, e acções em POST
        if metodo == 'GET':
            self._log_view(request)
        elif metodo == 'POST':
            self._log_post(request)

    def _log_view(self, request):
        """Regista visualização de página."""
        path = request.path
        # Ignorar AJAX e requisições internas
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        if '/api/' in path:
            return

        from .models import registrar_log
        # Descrição amigável
        descricao = f"Acedeu a {path}"
        modulo = getattr(request, '_log_modulo', 'sistema')
        registrar_log(request, 'VIEW', modulo, descricao)

    def _log_post(self, request):
        """Regista acções POST específicas."""
        path = request.path
        from .models import registrar_log
        modulo = getattr(request, '_log_modulo', 'sistema')

        # Detetar acção com base no path
        if '/cancelar' in path or '/cancel' in path:
            accao = 'CANCEL'
        elif '/aprovar' in path or '/approve' in path:
            accao = 'APPROVE'
        elif '/rejeitar' in path or '/reject' in path:
            accao = 'REJECT'
        elif '/eliminar' in path or '/delete' in path:
            accao = 'DELETE'
        elif '/enviar-email' in path or '/send-email' in path:
            accao = 'SEND_EMAIL'
        elif '/criar' in path or '/create' in path or '/novo' in path or '/new' in path:
            accao = 'CREATE'
        elif '/editar' in path or '/edit' in path or '/actualizar' in path:
            accao = 'EDIT'
        elif '/exportar' in path or '/export' in path or '/excel' in path or '/pdf' in path:
            accao = 'EXPORT'
        else:
            # Se for POST noutro endpoint, regista como EDIT genérico
            accao = 'EDIT'

        descricao = f"{accao} — {path}"
        registrar_log(request, accao, modulo, descricao)
