"""
Middleware para verificar automaticamente a expiração da sessão e registar logs de atividade.
"""
import logging
import re
from django.shortcuts import redirect
from django.utils import timezone
from .auth_decorators import sessao_expirada, limpar_sessao

session_logger = logging.getLogger('users.session')

# Módulos de negócio bloqueados quando a Banca está suspensa
_MODULOS_NEGOCIO_BLOQUEADOS = ('/rh/', '/financeiro/', '/aduaneiro/', '/clientes/')

# Módulos permitidos para despachante com Banca suspensa
_MODULOS_PERMITIDOS_BANCA_SUSPENSA = ('/dashboard/', '/governanca/', '/users/',
                                       '/login/', '/logout/', '/static/', '/media/')


class SessionExpirationMiddleware:
    """
    Middleware que verifica se a sessão expirou e redireciona para login.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Não verificar sessão para páginas públicas
        public_paths = ['/login/', '/logout/', '/static/', '/media/', '/admin/']
        
        # Endpoints de sessão (status/renovar) — não bloquear
        session_api_paths = ['/users/api/sessao-status/', '/users/api/renovar-sessao/',
                             '/session-status/', '/extend-session/']
        
        # Verificar se o path é público
        if any(request.path.startswith(path) for path in public_paths):
            return self.get_response(request)
        
        # Para endpoints de sessão, apenas verificar se existe sessão (não expirar)
        if any(request.path.startswith(path) for path in session_api_paths):
            return self.get_response(request)
        
        # Verificar se há sessão ativa
        if request.session.get('usuario_id'):
            usuario_id = request.session.get('usuario_id')
            tipo_usuario = request.session.get('tipo_usuario', 'desconhecido')

            # Verificar se a sessão expirou
            if sessao_expirada(request):
                session_logger.warning(
                    'SESSAO_EXPIRADA: usuario_id=%s tipo=%s path=%s — redirecionando para login',
                    usuario_id, tipo_usuario, request.path
                )
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

            # ── DESPACHANTE (tipo_usuario == 'usuario') ──
            if tipo_usuario == 'usuario':
                from .models import Usuario
                try:
                    u = Usuario.objects.get(pk=usuario_id)
                    if u.status != 'Ativo':
                        session_logger.warning(
                            'UTILIZADOR_INATIVO: usuario_id=%s email=%s status=%s path=%s — terminando sessao',
                            usuario_id, u.email, u.status, request.path
                        )
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

                    # Verificar se a Banca está ativa (apenas para não-admin)
                    if u.papel != 'Administrador':
                        from rh.models import Banca
                        banca = Banca.objects.filter(usuario_id=usuario_id).first()
                        if banca and not banca.ativa:
                            path = request.path
                            # Permitir acesso a perfil, governança, dashboard
                            if any(path.startswith(p) for p in _MODULOS_PERMITIDOS_BANCA_SUSPENSA):
                                pass  # permitir
                            elif any(path.startswith(p) for p in _MODULOS_NEGOCIO_BLOQUEADOS):
                                session_logger.warning(
                                    'BANCA_SUSPENSA_BLOQUEIO: usuario_id=%s banca=%s path=%s',
                                    usuario_id, banca.id, path
                                )
                                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                    from django.http import JsonResponse
                                    return JsonResponse({
                                        'error': 'A sua instituição está suspensa. Acesso ao negócio bloqueado.',
                                        'redirect': '/dashboard/'
                                    }, status=403)
                                from django.contrib import messages
                                messages.error(
                                    request,
                                    "A sua instituição está suspensa. Acesso ao módulo de negócio bloqueado. "
                                    "Contacte o administrador para regularizar a situação."
                                )
                                return redirect('dashboard')

                    # Verificar se Colaborador Institucional perdeu a função
                    if u.papel == 'Colaborador Institucional' and not u.funcao_id:
                        session_logger.warning(
                            'FUNCAO_REMOVIDA: usuario_id=%s email=%s path=%s — terminando sessao',
                            usuario_id, u.email, request.path
                        )
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
                    session_logger.error(
                        'UTILIZADOR_NAO_ENCONTRADO: usuario_id=%s path=%s — sessao invalida',
                        usuario_id, request.path
                    )
                    pass

            # ── COLABORADOR (tipo_usuario == 'colaborador') ──
            elif tipo_usuario == 'colaborador':
                colaborador_id = request.session.get('colaborador_id')
                if colaborador_id:
                    from rh.models import Colaborador
                    try:
                        c = Colaborador.objects.get(pk=colaborador_id)
                        if c.estado != 'Ativo':
                            session_logger.warning(
                                'COLABORADOR_INATIVO: colaborador_id=%s email=%s estado=%s path=%s — terminando sessao',
                                colaborador_id, c.email, c.estado, request.path
                            )
                            from .models import registrar_log
                            registrar_log(request, 'LOGOUT', 'users',
                                          f"Sessão terminada — colaborador {c.estado.lower()}: {c.email}")
                            limpar_sessao(request)
                            from django.contrib import messages
                            messages.error(
                                request,
                                "A sua conta de colaborador encontra-se " + c.estado.lower() + ". Entre em contacto com o seu responsável."
                            )
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                from django.http import JsonResponse
                                return JsonResponse({
                                    'error': 'Conta de colaborador ' + c.estado.lower(),
                                    'redirect': '/login/'
                                }, status=401)
                            return redirect('login')

                        # Verificar se a Banca do colaborador está ativa
                        if c.banca and not c.banca.ativa:
                            session_logger.warning(
                                'BANCA_SUSPENSA_COLAB: colaborador_id=%s banca=%s path=%s — terminando sessao',
                                colaborador_id, c.banca.id, request.path
                            )
                            from .models import registrar_log
                            registrar_log(request, 'LOGOUT', 'users',
                                          f"Sessão terminada — banca suspensa: {c.banca.nome}")
                            limpar_sessao(request)
                            from django.contrib import messages
                            messages.error(
                                request,
                                "A instituição à qual pertence está suspensa. "
                                "Contacte o responsável da instituição."
                            )
                            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                                from django.http import JsonResponse
                                return JsonResponse({
                                    'error': 'Instituição suspensa',
                                    'redirect': '/login/'
                                }, status=401)
                            return redirect('login')

                    except Colaborador.DoesNotExist:
                        session_logger.error(
                            'COLABORADOR_NAO_ENCONTRADO: colaborador_id=%s path=%s — sessao invalida',
                            colaborador_id, request.path
                        )
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

# Descrições legíveis para visualizações de páginas (GET)
_DESCOES_VIEW = {
    '/dashboard/': 'Visualizou o dashboard principal',
    '/rh/presencas/': 'Visualizou o controlo de presenças e férias',
    '/rh/ferias/': 'Visualizou o mapa de férias',
    '/rh/colaboradores/': 'Visualizou a lista de colaboradores',
    '/rh/vagas/': 'Visualizou as vagas de emprego',
    '/rh/recrutamento/': 'Visualizou o recrutamento',
    '/rh/avaliacoes/': 'Visualizou as avaliações de desempenho',
    '/rh/salarios/': 'Visualizou o processamento salarial',
    '/rh/subsidios/': 'Visualizou os subsídios',
    '/financeiro/facturas/': 'Visualizou as facturas',
    '/financeiro/recibos/': 'Visualizou os recibos',
    '/financeiro/notas-credito/': 'Visualizou as notas de crédito',
    '/financeiro/notas-debito/': 'Visualizou as notas de débito',
    '/financeiro/requisicoes-fundo/': 'Visualizou as requisições de fundo',
    '/governanca/': 'Visualizou o módulo de governança',
    '/aduaneiro/declaracoes/': 'Visualizou as declarações únicas',
    '/logs/': 'Visualizou os logs de actividade',
    '/relatorios/': 'Visualizou os relatórios',
}

# Padrões regex para páginas com ID específico (GET)
_DESCOES_VIEW_REGEX = [
    (r'^/rh/colaboradores/\d+/editar/$', 'Visualizou formulário de edição do colaborador'),
    (r'^/rh/colaboradores/\d+/$', 'Visualizou detalhes do colaborador'),
    (r'^/rh/vagas/\d+/$', 'Visualizou detalhes da vaga'),
    (r'^/rh/recrutamento/\d+/$', 'Visualizou detalhe do recrutamento'),
    (r'^/rh/avaliacoes/\d+/$', 'Visualizou detalhes da avaliação'),
    (r'^/clientes/\d+/editar/$', 'Visualizou formulário de edição do cliente'),
    (r'^/clientes/\d+/$', 'Visualizou detalhes do cliente'),
    (r'^/financeiro/facturas/\d+/$', 'Visualizou detalhes da factura'),
    (r'^/financeiro/recibos/\d+/$', 'Visualizou detalhes do recibo'),
    (r'^/financeiro/requisicoes-fundo/\d+/$', 'Visualizou detalhes da requisição de fundo'),
    (r'^/aduaneiro/declaracoes/\d+/$', 'Visualizou detalhes da declaração única'),
]

# Mapeamento de padrões de URL para descrições de acções POST
# Ordem: (padrão_regex, acção, descrição)
# A descrição pode conter {modulo} que será substituído pelo nome do módulo
_POST_DESCOES = [
    # RH — Presenças e Férias
    (r'/rh/presencas/registar/', 'CREATE', 'Registou uma presença'),
    (r'/rh/presencas/\d+/aprovar/', 'APPROVE', 'Aprovou um registo de presença'),
    (r'/rh/presencas/\d+/rejeitar/', 'REJECT', 'Rejeitou um registo de presença'),
    (r'/rh/presencas/\d+/apagar/', 'DELETE', 'Removeu um registo de presença'),
    (r'/rh/ferias/pedir/', 'CREATE', 'Submeteu um pedido de férias'),
    (r'/rh/ferias/\d+/aprovar/', 'APPROVE', 'Aprovou um pedido de férias'),
    (r'/rh/ferias/\d+/rejeitar/', 'REJECT', 'Rejeitou um pedido de férias'),
    (r'/rh/ferias/\d+/apagar/', 'DELETE', 'Removeu um pedido de férias'),

    # RH — Colaboradores
    (r'/rh/colaboradores/criar/', 'CREATE', 'Cadastrou um novo colaborador'),
    (r'/rh/colaboradores/\d+/editar/', 'EDIT', 'Editou dados do colaborador'),
    (r'/rh/colaboradores/\d+/eliminar/', 'DELETE', 'Removeu um colaborador'),
    (r'/rh/colaboradores/\d+/reativar/', 'EDIT', 'Reativou um colaborador'),

    # RH — Vagas
    (r'/rh/vagas/criar/', 'CREATE', 'Criou uma nova vaga de emprego'),
    (r'/rh/vagas/\d+/editar/', 'EDIT', 'Editou uma vaga de emprego'),
    (r'/rh/vagas/\d+/eliminar/', 'DELETE', 'Removeu uma vaga'),
    (r'/rh/vagas/\d+/estado/', 'EDIT', 'Alterou o estado de uma vaga'),

    # RH — Avaliações
    (r'/rh/avaliacoes/\d+/editar/', 'EDIT', 'Editou uma avaliação de desempenho'),

    # Clientes
    (r'/clientes/criar/', 'CREATE', 'Cadastrou um novo cliente'),
    (r'/clientes/\d+/editar/', 'EDIT', 'Editou dados do cliente'),
    (r'/clientes/\d+/eliminar/', 'DELETE', 'Removeu um cliente'),

    # Financeiro — Facturas
    (r'/financeiro/facturas/criar/', 'CREATE', 'Emitiu uma nova factura'),
    (r'/financeiro/facturas/\d+/editar/', 'EDIT', 'Editou uma factura'),
    (r'/financeiro/facturas/\d+/eliminar/', 'DELETE', 'Removeu uma factura'),
    (r'/financeiro/facturas/\d+/cancelar/', 'CANCEL', 'Cancelou uma factura'),
    (r'/financeiro/facturas/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou factura por email'),
    (r'/financeiro/facturas/\d+/pdf/', 'EXPORT', 'Exportou factura em PDF'),

    # Financeiro — Recibos
    (r'/financeiro/recibos/criar/', 'CREATE', 'Emitiu um novo recibo'),
    (r'/financeiro/recibos/\d+/editar/', 'EDIT', 'Editou um recibo'),
    (r'/financeiro/recibos/\d+/cancelar/', 'CANCEL', 'Cancelou um recibo'),

    # Financeiro — Requisições de Fundo
    (r'/financeiro/requisicoes-fundo/criar/', 'CREATE', 'Criou uma requisição de fundo'),
    (r'/financeiro/requisicoes-fundo/\d+/editar/', 'EDIT', 'Editou uma requisição de fundo'),
    (r'/financeiro/requisicoes-fundo/\d+/aprovar/', 'APPROVE', 'Aprovou uma requisição de fundo'),
    (r'/financeiro/requisicoes-fundo/\d+/rejeitar/', 'REJECT', 'Rejeitou uma requisição de fundo'),

    # Aduaneiro
    (r'/aduaneiro/declaracoes/criar/', 'CREATE', 'Criou uma declaração única'),
    (r'/aduaneiro/declaracoes/\d+/editar/', 'EDIT', 'Editou uma declaração única'),
    (r'/aduaneiro/declaracoes/\d+/eliminar/', 'DELETE', 'Removeu uma declaração única'),

    # Utilizadores / Sistema
    (r'/users/criar/', 'CREATE', 'Criou um novo utilizador'),
    (r'/users/\d+/editar/', 'EDIT', 'Editou dados do utilizador'),
    (r'/users/\d+/estado/', 'EDIT', 'Alterou estado do utilizador'),
]

# Descrição genérica para POST sem pattern específico
_POST_FALLBACK = {
    'CREATE': 'Criou um registo',
    'EDIT': 'Editou um registo',
    'DELETE': 'Removeu um registo',
    'APPROVE': 'Aprovou um registo',
    'REJECT': 'Rejeitou um registo',
    'CANCEL': 'Cancelou um registo',
    'SEND_EMAIL': 'Enviou um email',
    'EXPORT': 'Exportou dados',
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
        """Regista visualização de página com descrição legível."""
        path = request.path
        # Ignorar AJAX e requisições internas
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        if '/api/' in path:
            return

        from .models import registrar_log
        modulo = getattr(request, '_log_modulo', 'sistema')

        # Procurar descrição legível
        descricao = _DESCOES_VIEW.get(path)
        if not descricao:
            for pattern, d in _DESCOES_VIEW_REGEX:
                if re.search(pattern, path):
                    descricao = d
                    break

        if not descricao:
            # Fallback: extrair nome do módulo e últimos segmentos do path
                nome_modulo = {
                    'financeiro': 'Financeiro', 'clientes': 'Clientes',
                    'rh': 'RH', 'governanca': 'Governança',
                    'aduaneiro': 'Aduaneiro', 'users': 'Utilizadores',
                }.get(modulo, 'Sistema')
                descricao = f'Visualizou página de {nome_modulo}'

        registrar_log(request, 'VIEW', modulo, descricao)

    def _log_post(self, request):
        """Regista acções POST com descrição legível."""
        path = request.path
        from .models import registrar_log
        modulo = getattr(request, '_log_modulo', 'sistema')

        # Procurar pattern específico
        accao = None
        descricao = None
        for pattern, accao_pt, desc in _POST_DESCOES:
            if re.search(pattern, path):
                accao = accao_pt
                descricao = desc
                break

        if not accao:
            # Fallback: detetar acção por palavras-chave no path
            if '/cancelar' in path or '/cancel' in path:
                accao = 'CANCEL'
            elif '/aprovar' in path or '/approve' in path:
                accao = 'APPROVE'
            elif '/rejeitar' in path or '/reject' in path:
                accao = 'REJECT'
            elif '/eliminar' in path or '/delete' in path or '/apagar' in path:
                accao = 'DELETE'
            elif '/enviar-email' in path or '/send-email' in path:
                accao = 'SEND_EMAIL'
            elif '/criar' in path or '/create' in path or '/novo' in path or '/new' in path or '/registar' in path:
                accao = 'CREATE'
            elif '/editar' in path or '/edit' in path or '/actualizar' in path:
                accao = 'EDIT'
            elif '/exportar' in path or '/export' in path or '/excel' in path or '/pdf' in path:
                accao = 'EXPORT'
            else:
                accao = 'EDIT'

            descricao = _POST_FALLBACK.get(accao, f'{accao} — {path}')

        registrar_log(request, accao, modulo, descricao)
