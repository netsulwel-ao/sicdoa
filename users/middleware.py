"""
Middleware para verificar automaticamente a expiração da sessão e registar logs de atividade.
"""
import json
import logging
import re
from django.shortcuts import redirect
from django.urls import resolve, Resolver404
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
                    if u.papel not in ('Administrador', 'Super Administrador'):
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
                    limpar_sessao(request)
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'error': 'Sessão inválida',
                            'redirect': '/login/'
                        }, status=401)
                    return redirect('login')

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
                        limpar_sessao(request)
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'error': 'Sessão inválida',
                                'redirect': '/login/'
                            }, status=401)
                        return redirect('login')
        
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
    '/du/': 'aduaneiro',
    '/aduaneiro/': 'aduaneiro',
    '/users/': 'users',
    '/login': 'users',
    '/logout': 'users',
}

_MODULO_NOMES = {
    'users': 'Utilizadores',
    'clientes': 'Clientes',
    'financeiro': 'Financeiro',
    'governanca': 'Governança',
    'rh': 'Recursos Humanos',
    'aduaneiro': 'Aduaneiro',
    'sistema': 'Sistema',
}

# ────────────────────────────────────────────────────────────────────────────
# Registo de entidades: url_name resolvido → (modelo, kwarg, ...)
# Permite gerar descrições detalhadas com o nome do registo afetado.
#   accao       → código da acção (CREATE/EDIT/DELETE/...)
#   modelo      → caminho do modelo, ex. 'clientes.models.Cliente'
#   kw          → chave do URL (pk, du_uuid, banca_id, linha_id, ...)
#   post        → campos do POST (form) usados para obter o nome em criações
#   post_fk     → campos FK do POST: valor → modelo do qual obter o nome
#   template    → descrição detalhada (contém {nome})
#   geral       → descrição sem nome (fallback)
# ────────────────────────────────────────────────────────────────────────────
_REGISTO_ENTIDADES = {
    # ── Clientes ──────────────────────────────────────────────────────────
    'clientes:criar':   dict(accao='CREATE', modelo='clientes.models.Cliente', post=('nome',),
                             template='Criou um novo cliente — {nome}', geral='Criou um novo cliente'),
    'clientes:editar':  dict(accao='EDIT', modelo='clientes.models.Cliente', kw='pk', post=('nome',),
                             template='Editou o cliente {nome}', geral='Editou dados de um cliente'),
    'clientes:excluir': dict(accao='DELETE', modelo='clientes.models.Cliente', kw='pk',
                             template='Eliminou o cliente {nome}', geral='Eliminou um cliente'),

    # ── Aduaneiro (DU) ────────────────────────────────────────────────────
    'aduaneiro:du_apagar': dict(accao='DELETE', modelo='aduaneiro.models.DeclaracaoUnica', kw='du_uuid',
                                template='Eliminou a DU {nome}', geral='Eliminou uma DU'),
    'aduaneiro:du_alterar_status': dict(accao='EDIT', modelo='aduaneiro.models.DeclaracaoUnica', kw='du_uuid',
                                        template='Alterou o estado da DU {nome}', geral='Alterou o estado de uma DU'),
    'aduaneiro:criar_cliente_rapido': dict(accao='CREATE', modelo='clientes.models.Cliente',
                                           json=True, json_campos=('nome',), post=('nome',),
                                           template='Criou um novo cliente — {nome}', geral='Criou um novo cliente'),

    # ── RH — Colaboradores / Bancas / Filiais ─────────────────────────────
    'rh_colaborador_novo': dict(accao='CREATE', modelo='rh.models.Colaborador', post=('nome',),
                                template='Cadastrou um novo colaborador — {nome}', geral='Cadastrou um novo colaborador'),
    'rh_colaborador_editar': dict(accao='EDIT', modelo='rh.models.Colaborador', kw='pk', post=('nome',),
                                  template='Editou o colaborador {nome}', geral='Editou dados de um colaborador'),
    'rh_colaborador_apagar': dict(accao='DELETE', modelo='rh.models.Colaborador', kw='pk',
                                  template='Removeu o colaborador {nome}', geral='Removeu um colaborador'),
    'rh_colaborador_reenviar_email': dict(accao='SEND_EMAIL', modelo='rh.models.Colaborador', kw='pk',
                                          template='Reenviou credenciais ao colaborador {nome}',
                                          geral='Reenviou credenciais a um colaborador'),
    'rh_colaborador_cargo': dict(accao='EDIT', modelo='rh.models.Colaborador', kw='pk',
                                 template='Alterou o cargo do colaborador {nome}', geral='Alterou o cargo de um colaborador'),
    'rh_banca_criar': dict(accao='CREATE', modelo='rh.models.Banca', post=('nome',),
                           template='Criou a banca {nome}', geral='Criou a banca'),
    'rh_banca_editar': dict(accao='EDIT', modelo='rh.models.Banca', post=('nome',),
                            template='Editou a banca {nome}', geral='Editou a banca'),
    'rh_filial_nova': dict(accao='CREATE', modelo='rh.models.FilialBanca', post=('provincia', 'municipio'),
                           template='Criou a filial de {nome}', geral='Criou uma nova filial'),
    'rh_filial_editar': dict(accao='EDIT', modelo='rh.models.FilialBanca', kw='pk',
                             template='Editou a filial {nome}', geral='Editou uma filial'),
    'rh_filial_apagar': dict(accao='DELETE', modelo='rh.models.FilialBanca', kw='pk',
                             template='Eliminou a filial {nome}', geral='Eliminou uma filial'),

    # ── RH — Cargos / Subsídios / Salários / Vagas ────────────────────────
    'rh_cargo_novo': dict(accao='CREATE', modelo='rh.models.CargoBanca', post=('nome',),
                          template='Criou o cargo {nome}', geral='Criou um novo cargo'),
    'rh_cargo_editar': dict(accao='EDIT', modelo='rh.models.CargoBanca', kw='pk', post=('nome',),
                            template='Editou o cargo {nome}', geral='Editou um cargo'),
    'rh_cargo_eliminar': dict(accao='DELETE', modelo='rh.models.CargoBanca', kw='pk',
                              template='Eliminou o cargo {nome}', geral='Eliminou um cargo'),
    'rh_subsidio_novo': dict(accao='CREATE', modelo='rh.models.Subsidio', post=('nome',),
                             template='Criou o subsídio {nome}', geral='Criou um novo subsídio'),
    'rh_subsidio_editar': dict(accao='EDIT', modelo='rh.models.Subsidio', kw='pk', post=('nome',),
                               template='Editou o subsídio {nome}', geral='Editou um subsídio'),
    'rh_subsidio_apagar': dict(accao='DELETE', modelo='rh.models.Subsidio', kw='pk',
                               template='Eliminou o subsídio {nome}', geral='Eliminou um subsídio'),
    'rh_salario_novo': dict(accao='CREATE', modelo='rh.models.ProcessamentoSalarial', post_join=('mes', 'ano'),
                            template='Criou o processamento salarial de {nome}', geral='Criou um processamento salarial'),
    'rh_salario_apagar': dict(accao='DELETE', modelo='rh.models.ProcessamentoSalarial', kw='pk',
                              template='Eliminou o processamento salarial {nome}',
                              geral='Eliminou um processamento salarial'),
    'rh_vaga_nova': dict(accao='CREATE', modelo='rh.models.Vaga', post=('titulo',),
                         template='Criou a vaga {nome}', geral='Criou uma nova vaga de emprego'),
    'rh_vaga_editar': dict(accao='EDIT', modelo='rh.models.Vaga', kw='pk', post=('titulo',),
                           template='Editou a vaga {nome}', geral='Editou uma vaga de emprego'),
    'rh_vaga_eliminar': dict(accao='DELETE', modelo='rh.models.Vaga', kw='pk',
                             template='Eliminou a vaga {nome}', geral='Eliminou uma vaga'),

    # ── RH — Recrutamento / Avaliações ────────────────────────────────────
    'rh_candidatura_estado': dict(accao='EDIT', modelo='rh.models.Candidatura', kw='pk',
                                  template='Alterou o estado da candidatura {nome}',
                                  geral='Alterou o estado de uma candidatura'),
    'rh_entrevista_nova': dict(accao='CREATE', modelo='rh.models.Entrevista', kw='candidatura_pk',
                               template='Criou uma entrevista para {nome}', geral='Criou uma entrevista'),
    'rh_entrevista_resultado': dict(accao='EDIT', modelo='rh.models.Entrevista', kw='pk',
                                    template='Registou o resultado da entrevista {nome}',
                                    geral='Registou o resultado de uma entrevista'),
    'rh_integracao_nova': dict(accao='CREATE', modelo='rh.models.PlanoIntegracao', kw='candidatura_pk',
                               template='Criou um plano de integração para {nome}',
                               geral='Criou um plano de integração'),
    'rh_ciclo_novo': dict(accao='CREATE', modelo='rh.models.CicloAvaliacao', post=('nome',),
                          template='Criou o ciclo de avaliação {nome}', geral='Criou um ciclo de avaliação'),
    'rh_ciclo_editar': dict(accao='EDIT', modelo='rh.models.CicloAvaliacao', kw='pk', post=('nome',),
                            template='Editou o ciclo de avaliação {nome}', geral='Editou um ciclo de avaliação'),
    'rh_ciclo_apagar': dict(accao='DELETE', modelo='rh.models.CicloAvaliacao', kw='pk',
                            template='Eliminou o ciclo de avaliação {nome}', geral='Eliminou um ciclo de avaliação'),
    'rh_avaliacao_nova': dict(accao='CREATE', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                              template='Criou uma avaliação de desempenho', geral='Criou uma avaliação de desempenho'),
    'rh_avaliacao_editar': dict(accao='EDIT', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                                template='Editou uma avaliação de desempenho', geral='Editou uma avaliação de desempenho'),
    'rh_avaliacao_apagar': dict(accao='DELETE', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                                template='Eliminou uma avaliação de desempenho',
                                geral='Eliminou uma avaliação de desempenho'),

    # ── RH — Presenças / Férias ───────────────────────────────────────────
    'rh_presenca_registar': dict(accao='CREATE', modelo='rh.models.RegistoPresenca',
                                 post_fk={'colaborador': 'rh.models.Colaborador'}, post=('data',),
                                 template='Registou a presença de {nome}', geral='Registou uma presença'),
    'rh_presenca_aprovar': dict(accao='APPROVE', modelo='rh.models.RegistoPresenca', kw='pk',
                                template='Aprovou o registo de presença de {nome}',
                                geral='Aprovou um registo de presença'),
    'rh_presenca_apagar': dict(accao='DELETE', modelo='rh.models.RegistoPresenca', kw='pk',
                               template='Removeu o registo de presença de {nome}',
                               geral='Removeu um registo de presença'),
    'rh_ferias_pedir': dict(accao='CREATE', modelo='rh.models.PedidoFerias',
                            post_fk={'colaborador': 'rh.models.Colaborador'},
                            template='Submeteu um pedido de férias para {nome}',
                            geral='Submeteu um pedido de férias'),
    'rh_ferias_aprovar': dict(accao='APPROVE', modelo='rh.models.PedidoFerias', kw='pk',
                              template='Aprovou o pedido de férias de {nome}',
                              geral='Aprovou um pedido de férias'),
    'rh_ferias_apagar': dict(accao='DELETE', modelo='rh.models.PedidoFerias', kw='pk',
                             template='Removeu o pedido de férias de {nome}',
                             geral='Removeu um pedido de férias'),

    # ── RH — Institucional (espelho das acções principais) ────────────────
    'rh_inst_subsidio_novo': dict(accao='CREATE', modelo='rh.models.Subsidio', post=('nome',),
                                  template='Criou o subsídio {nome}', geral='Criou um novo subsídio'),
    'rh_inst_subsidio_editar': dict(accao='EDIT', modelo='rh.models.Subsidio', kw='pk', post=('nome',),
                                    template='Editou o subsídio {nome}', geral='Editou um subsídio'),
    'rh_inst_subsidio_apagar': dict(accao='DELETE', modelo='rh.models.Subsidio', kw='pk',
                                    template='Eliminou o subsídio {nome}', geral='Eliminou um subsídio'),
    'rh_inst_salario_novo': dict(accao='CREATE', modelo='rh.models.ProcessamentoSalarial', post_join=('mes', 'ano'),
                                 template='Criou o processamento salarial de {nome}',
                                 geral='Criou um processamento salarial'),
    'rh_inst_salario_apagar': dict(accao='DELETE', modelo='rh.models.ProcessamentoSalarial', kw='pk',
                                   template='Eliminou o processamento salarial {nome}',
                                   geral='Eliminou um processamento salarial'),
    'rh_inst_vaga_nova': dict(accao='CREATE', modelo='rh.models.Vaga', post=('titulo',),
                              template='Criou a vaga {nome}', geral='Criou uma nova vaga de emprego'),
    'rh_inst_vaga_editar': dict(accao='EDIT', modelo='rh.models.Vaga', kw='pk', post=('titulo',),
                                template='Editou a vaga {nome}', geral='Editou uma vaga de emprego'),
    'rh_inst_vaga_eliminar': dict(accao='DELETE', modelo='rh.models.Vaga', kw='pk',
                                  template='Eliminou a vaga {nome}', geral='Eliminou uma vaga'),
    'rh_inst_presenca_registar': dict(accao='CREATE', modelo='rh.models.RegistoPresenca',
                                      post_fk={'colaborador': 'rh.models.Colaborador'}, post=('data',),
                                      template='Registou a presença de {nome}', geral='Registou uma presença'),
    'rh_inst_presenca_aprovar': dict(accao='APPROVE', modelo='rh.models.RegistoPresenca', kw='pk',
                                     template='Aprovou o registo de presença de {nome}',
                                     geral='Aprovou um registo de presença'),
    'rh_inst_presenca_apagar': dict(accao='DELETE', modelo='rh.models.RegistoPresenca', kw='pk',
                                    template='Removeu o registo de presença de {nome}',
                                    geral='Removeu um registo de presença'),
    'rh_inst_ferias_pedir': dict(accao='CREATE', modelo='rh.models.PedidoFerias',
                                 post_fk={'colaborador': 'rh.models.Colaborador'},
                                 template='Submeteu um pedido de férias para {nome}',
                                 geral='Submeteu um pedido de férias'),
    'rh_inst_ferias_aprovar': dict(accao='APPROVE', modelo='rh.models.PedidoFerias', kw='pk',
                                   template='Aprovou o pedido de férias de {nome}',
                                   geral='Aprovou um pedido de férias'),
    'rh_inst_ferias_apagar': dict(accao='DELETE', modelo='rh.models.PedidoFerias', kw='pk',
                                  template='Removeu o pedido de férias de {nome}',
                                  geral='Removeu um pedido de férias'),
    'rh_inst_ciclo_novo': dict(accao='CREATE', modelo='rh.models.CicloAvaliacao', post=('nome',),
                               template='Criou o ciclo de avaliação {nome}', geral='Criou um ciclo de avaliação'),
    'rh_inst_avaliacao_nova': dict(accao='CREATE', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                                   template='Criou uma avaliação de desempenho',
                                   geral='Criou uma avaliação de desempenho'),
    'rh_inst_avaliacao_editar': dict(accao='EDIT', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                                     template='Editou uma avaliação de desempenho',
                                     geral='Editou uma avaliação de desempenho'),
    'rh_inst_avaliacao_apagar': dict(accao='DELETE', modelo='rh.models.Avaliacao', kw='ciclo_pk',
                                     template='Eliminou uma avaliação de desempenho',
                                     geral='Eliminou uma avaliação de desempenho'),

    # ── Financeiro — Requisições de Fundo ─────────────────────────────────
    'financeiro:requisicao_criar': dict(accao='CREATE', modelo='financeiro.models.RequisicaoFundo',
                                        post_fk={'cliente': 'clientes.models.Cliente'},
                                        post=('observacoes', 'processo_aduaneiro'),
                                        template='Criou a requisição de fundo para {nome}',
                                        geral='Criou uma requisição de fundo'),
    'financeiro:requisicao_editar': dict(accao='EDIT', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                         template='Editou a requisição de fundo {nome}',
                                         geral='Editou uma requisição de fundo'),
    'financeiro:requisicao_cancelar': dict(accao='CANCEL', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                           template='Cancelou a requisição de fundo {nome}',
                                           geral='Cancelou uma requisição de fundo'),
    'financeiro:requisicao_eliminar': dict(accao='DELETE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                           template='Eliminou a requisição de fundo {nome}',
                                           geral='Eliminou uma requisição de fundo'),
    'financeiro:requisicao_aceitar': dict(accao='APPROVE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                          template='Aprovou a requisição de fundo {nome}',
                                          geral='Aprovou uma requisição de fundo'),
    'financeiro:requisicao_rejeitar': dict(accao='REJECT', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                           template='Rejeitou a requisição de fundo {nome}',
                                           geral='Rejeitou uma requisição de fundo'),
    'financeiro:requisicao_criar_factura': dict(accao='CREATE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                                template='Criou uma factura a partir da requisição {nome}',
                                                geral='Criou uma factura a partir da requisição'),
    'financeiro:requisicao_criar_factura_recibo': dict(accao='CREATE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                                       template='Criou uma factura-recibo a partir da requisição {nome}',
                                                       geral='Criou uma factura-recibo a partir da requisição'),
    'financeiro:requisicao_linha_adicionar': dict(accao='CREATE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                                  template='Adicionou uma linha à requisição {nome}',
                                                  geral='Adicionou uma linha à requisição'),
    'financeiro:requisicao_linha_editar': dict(accao='EDIT', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                               template='Editou uma linha da requisição {nome}',
                                               geral='Editou uma linha da requisição'),
    'financeiro:requisicao_linha_eliminar': dict(accao='DELETE', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                                 template='Eliminou uma linha da requisição {nome}',
                                                 geral='Eliminou uma linha da requisição'),
    'financeiro:requisicao_enviar_email': dict(accao='SEND_EMAIL', modelo='financeiro.models.RequisicaoFundo', kw='pk',
                                               template='Reenviou a requisição de fundo {nome} por email',
                                               geral='Reenviou uma requisição por email'),

    # ── Financeiro — Facturas ─────────────────────────────────────────────
    'financeiro:factura_editar': dict(accao='EDIT', modelo='financeiro.models.FacturaCliente', kw='pk',
                                      template='Editou a factura {nome}', geral='Editou uma factura'),
    'financeiro:factura_cancelar': dict(accao='CANCEL', modelo='financeiro.models.FacturaCliente', kw='pk',
                                        template='Cancelou a factura {nome}', geral='Cancelou uma factura'),
    'financeiro:factura_eliminar': dict(accao='DELETE', modelo='financeiro.models.FacturaCliente', kw='pk',
                                        template='Eliminou a factura {nome}', geral='Eliminou uma factura'),
    'financeiro:factura_enviar_email': dict(accao='SEND_EMAIL', modelo='financeiro.models.FacturaCliente', kw='pk',
                                            template='Reenviou a factura {nome} por email',
                                            geral='Reenviou uma factura por email'),

    # ── Financeiro — Recibos ──────────────────────────────────────────────
    'financeiro:recibo_criar': dict(accao='CREATE', modelo='financeiro.models.ReciboCliente',
                                    post_fk={'cliente': 'clientes.models.Cliente'},
                                    template='Emitiu o recibo para {nome}', geral='Emitiu um novo recibo'),
    'financeiro:recibo_editar': dict(accao='EDIT', modelo='financeiro.models.ReciboCliente', kw='pk',
                                     template='Editou o recibo {nome}', geral='Editou um recibo'),
    'financeiro:recibo_cancelar': dict(accao='CANCEL', modelo='financeiro.models.ReciboCliente', kw='pk',
                                       template='Cancelou o recibo {nome}', geral='Cancelou um recibo'),
    'financeiro:recibo_enviar_email': dict(accao='SEND_EMAIL', modelo='financeiro.models.ReciboCliente', kw='pk',
                                           template='Reenviou o recibo {nome} por email',
                                           geral='Reenviou um recibo por email'),

    # ── Financeiro — Notas de Crédito / Débito ────────────────────────────
    'financeiro:nota_credito_criar': dict(accao='CREATE', modelo='financeiro.models.NotaCredito',
                                          post_fk={'cliente': 'clientes.models.Cliente'},
                                          template='Criou a nota de crédito para {nome}',
                                          geral='Criou uma nota de crédito'),
    'financeiro:nota_credito_editar': dict(accao='EDIT', modelo='financeiro.models.NotaCredito', kw='pk',
                                           template='Editou a nota de crédito {nome}',
                                           geral='Editou uma nota de crédito'),
    'financeiro:nota_credito_aprovar': dict(accao='APPROVE', modelo='financeiro.models.NotaCredito', kw='pk',
                                            template='Aprovou a nota de crédito {nome}',
                                            geral='Aprovou uma nota de crédito'),
    'financeiro:nota_credito_rejeitar': dict(accao='REJECT', modelo='financeiro.models.NotaCredito', kw='pk',
                                             template='Rejeitou a nota de crédito {nome}',
                                             geral='Rejeitou uma nota de crédito'),
    'financeiro:nota_credito_cancelar': dict(accao='CANCEL', modelo='financeiro.models.NotaCredito', kw='pk',
                                             template='Cancelou a nota de crédito {nome}',
                                             geral='Cancelou uma nota de crédito'),
    'financeiro:nota_credito_eliminar': dict(accao='DELETE', modelo='financeiro.models.NotaCredito', kw='pk',
                                             template='Eliminou a nota de crédito {nome}',
                                             geral='Eliminou uma nota de crédito'),
    'financeiro:nota_credito_enviar_email': dict(accao='SEND_EMAIL', modelo='financeiro.models.NotaCredito', kw='pk',
                                                 template='Reenviou a nota de crédito {nome} por email',
                                                 geral='Reenviou uma nota de crédito por email'),
    'financeiro:nota_debito_criar': dict(accao='CREATE', modelo='financeiro.models.NotaDebito',
                                         post_fk={'cliente': 'clientes.models.Cliente'},
                                         template='Criou a nota de débito para {nome}',
                                         geral='Criou uma nota de débito'),
    'financeiro:nota_debito_editar': dict(accao='EDIT', modelo='financeiro.models.NotaDebito', kw='pk',
                                          template='Editou a nota de débito {nome}',
                                          geral='Editou uma nota de débito'),
    'financeiro:nota_debito_aprovar': dict(accao='APPROVE', modelo='financeiro.models.NotaDebito', kw='pk',
                                           template='Aprovou a nota de débito {nome}',
                                           geral='Aprovou uma nota de débito'),
    'financeiro:nota_debito_rejeitar': dict(accao='REJECT', modelo='financeiro.models.NotaDebito', kw='pk',
                                            template='Rejeitou a nota de débito {nome}',
                                            geral='Rejeitou uma nota de débito'),
    'financeiro:nota_debito_cancelar': dict(accao='CANCEL', modelo='financeiro.models.NotaDebito', kw='pk',
                                            template='Cancelou a nota de débito {nome}',
                                            geral='Cancelou uma nota de débito'),
    'financeiro:nota_debito_eliminar': dict(accao='DELETE', modelo='financeiro.models.NotaDebito', kw='pk',
                                            template='Eliminou a nota de débito {nome}',
                                            geral='Eliminou uma nota de débito'),
    'financeiro:nota_debito_enviar_email': dict(accao='SEND_EMAIL', modelo='financeiro.models.NotaDebito', kw='pk',
                                                template='Reenviou a nota de débito {nome} por email',
                                                geral='Reenviou uma nota de débito por email'),
    'financeiro:factura_recibo_editar': dict(accao='EDIT', modelo='financeiro.models.FacturaRecibo', kw='pk',
                                             template='Editou a factura-recibo {nome}',
                                             geral='Editou uma factura-recibo'),
    'financeiro:factura_recibo_cancelar': dict(accao='CANCEL', modelo='financeiro.models.FacturaRecibo', kw='pk',
                                               template='Cancelou a factura-recibo {nome}',
                                               geral='Cancelou uma factura-recibo'),

    # ── Utilizadores / Funções / Perfil ───────────────────────────────────
    'funcao_novo': dict(accao='CREATE', modelo='users.models.Funcao', post=('nome',),
                        template='Criou a função {nome}', geral='Criou uma nova função'),
    'funcao_editar': dict(accao='EDIT', modelo='users.models.Funcao', kw='pk', post=('nome',),
                          template='Editou a função {nome}', geral='Editou uma função'),
    'funcao_eliminar': dict(accao='DELETE', modelo='users.models.Funcao', kw='pk',
                            template='Eliminou a função {nome}', geral='Eliminou uma função'),
    'meu_perfil_guardar': dict(accao='EDIT', template='Actualizou o seu perfil', geral='Actualizou o seu perfil'),
    'meu_perfil_senha': dict(accao='EDIT', template='Alterou a sua senha', geral='Alterou a sua senha'),
    'meu_perfil_assinatura': dict(accao='EDIT', template='Actualizou a sua assinatura', geral='Actualizou a sua assinatura'),
    'meu_perfil_foto': dict(accao='EDIT', template='Actualizou a sua foto de perfil', geral='Actualizou a sua foto de perfil'),
    'meu_perfil_foto_remover': dict(accao='EDIT', template='Removeu a sua foto de perfil', geral='Removeu a sua foto de perfil'),
}

# Páginas de detalhe/edição (GET) cujas descrições incluem o nome da entidade.
_ALVO_VIEW = {
    'clientes:detalhes': ('clientes.models.Cliente', 'pk'),
    'clientes:editar': ('clientes.models.Cliente', 'pk'),
    'clientes:excluir': ('clientes.models.Cliente', 'pk'),
    'aduaneiro:du_detalhe': ('aduaneiro.models.DeclaracaoUnica', 'du_uuid'),
    'aduaneiro:du_editar': ('aduaneiro.models.DeclaracaoUnica', 'du_uuid'),
    'aduaneiro:du_historico': ('aduaneiro.models.DeclaracaoUnica', 'du_uuid'),
    'rh_colaborador_detalhe': ('rh.models.Colaborador', 'pk'),
    'rh_colaborador_editar': ('rh.models.Colaborador', 'pk'),
    'rh_colaborador_apagar': ('rh.models.Colaborador', 'pk'),
    'rh_filial_detalhe': ('rh.models.FilialBanca', 'pk'),
    'rh_filial_editar': ('rh.models.FilialBanca', 'pk'),
    'rh_filial_dashboard': ('rh.models.FilialBanca', 'pk'),
    'rh_filial_apagar': ('rh.models.FilialBanca', 'pk'),
    'rh_cargo_editar': ('rh.models.CargoBanca', 'pk'),
    'rh_salario_detalhe': ('rh.models.ProcessamentoSalarial', 'pk'),
    'rh_subsidio_editar': ('rh.models.Subsidio', 'pk'),
    'rh_vaga_editar': ('rh.models.Vaga', 'pk'),
    'rh_candidatura_detalhe': ('rh.models.Candidatura', 'pk'),
    'rh_ciclo_detalhe': ('rh.models.CicloAvaliacao', 'pk'),
    'funcao_editar': ('users.models.Funcao', 'pk'),
    'funcao_permissoes': ('users.models.Funcao', 'pk'),
    'financeiro:requisicao_detalhe': ('financeiro.models.RequisicaoFundo', 'pk'),
    'financeiro:requisicao_editar': ('financeiro.models.RequisicaoFundo', 'pk'),
    'financeiro:factura_detalhe': ('financeiro.models.FacturaCliente', 'pk'),
    'financeiro:factura_editar': ('financeiro.models.FacturaCliente', 'pk'),
    'financeiro:recibo_detalhe': ('financeiro.models.ReciboCliente', 'pk'),
    'financeiro:recibo_editar': ('financeiro.models.ReciboCliente', 'pk'),
    'financeiro:nota_credito_detalhe': ('financeiro.models.NotaCredito', 'pk'),
    'financeiro:nota_credito_editar': ('financeiro.models.NotaCredito', 'pk'),
    'financeiro:nota_debito_detalhe': ('financeiro.models.NotaDebito', 'pk'),
    'financeiro:nota_debito_editar': ('financeiro.models.NotaDebito', 'pk'),
    'financeiro:factura_recibo_detalhe': ('financeiro.models.FacturaRecibo', 'pk'),
    'financeiro:factura_recibo_editar': ('financeiro.models.FacturaRecibo', 'pk'),
}

# Descrições legíveis por view (GET). {nome} é usado nas páginas de detalhe.
_DESCOES_VIEW_POR_VIEW = {
    # Clientes
    'clientes:lista': 'Visualizou a lista de clientes',
    'clientes:criar': 'Visualizou o formulário de criação de cliente',
    'clientes:detalhes': 'Visualizou detalhes do cliente {nome}',
    'clientes:editar': 'Visualizou o formulário de edição do cliente {nome}',
    'clientes:excluir': 'Visualizou o formulário de exclusão do cliente {nome}',
    # Aduaneiro
    'aduaneiro:du': 'Visualizou o formulário de declaração única',
    'aduaneiro:du_editar': 'Visualizou o formulário de edição da DU {nome}',
    'aduaneiro:du_lista': 'Visualizou as declarações únicas',
    'aduaneiro:du_detalhe': 'Visualizou detalhes da DU {nome}',
    'aduaneiro:du_historico': 'Visualizou o histórico da DU {nome}',
    'aduaneiro:pauta_aduaneira': 'Visualizou a pauta aduaneira',
    # RH
    'rh_colaboradores': 'Visualizou a lista de colaboradores',
    'rh_colaborador_novo': 'Visualizou o formulário de criação de colaborador',
    'rh_colaborador_detalhe': 'Visualizou detalhes do colaborador {nome}',
    'rh_colaborador_editar': 'Visualizou o formulário de edição do colaborador {nome}',
    'rh_colaborador_apagar': 'Visualizou o formulário de exclusão do colaborador {nome}',
    'rh_banca': 'Visualizou a banca',
    'rh_banca_detalhe': 'Visualizou os detalhes da banca',
    'rh_banca_criar': 'Visualizou o formulário de criação da banca',
    'rh_banca_editar': 'Visualizou o formulário de edição da banca',
    'rh_filial_nova': 'Visualizou o formulário de criação de filial',
    'rh_filial_detalhe': 'Visualizou detalhes da filial {nome}',
    'rh_filial_editar': 'Visualizou o formulário de edição da filial {nome}',
    'rh_filial_dashboard': 'Visualizou o dashboard da filial {nome}',
    'rh_filial_apagar': 'Visualizou o formulário de exclusão da filial {nome}',
    'rh_cargos_lista': 'Visualizou os cargos da banca',
    'rh_cargo_novo': 'Visualizou o formulário de criação de cargo',
    'rh_cargo_editar': 'Visualizou o formulário de edição do cargo {nome}',
    'rh_presencas': 'Visualizou o controlo de presenças',
    'rh_presenca_registar': 'Visualizou o formulário de registo de presença',
    'rh_ferias': 'Visualizou o mapa de férias',
    'rh_ferias_pedir': 'Visualizou o formulário de pedido de férias',
    'rh_salarios': 'Visualizou o processamento salarial',
    'rh_salario_novo': 'Visualizou o formulário de processamento salarial',
    'rh_salario_detalhe': 'Visualizou detalhes do processamento salarial {nome}',
    'rh_subsidios': 'Visualizou os subsídios',
    'rh_subsidio_novo': 'Visualizou o formulário de criação de subsídio',
    'rh_subsidio_editar': 'Visualizou o formulário de edição do subsídio {nome}',
    'rh_vagas': 'Visualizou as vagas de emprego',
    'rh_vaga_nova': 'Visualizou o formulário de criação de vaga',
    'rh_vaga_editar': 'Visualizou o formulário de edição da vaga {nome}',
    'rh_candidaturas': 'Visualizou as candidaturas',
    'rh_candidatura_detalhe': 'Visualizou detalhes da candidatura {nome}',
    'rh_avaliacoes': 'Visualizou as avaliações de desempenho',
    'rh_ciclo_novo': 'Visualizou o formulário de criação de ciclo',
    'rh_ciclo_detalhe': 'Visualizou detalhes do ciclo de avaliação {nome}',
    'rh_avaliacao_nova': 'Visualizou o formulário de avaliação',
    'rh_avaliacao_detalhe': 'Visualizou uma avaliação de desempenho',
    'rh_inst_dashboard': 'Visualizou o dashboard institucional',
    'rh_banca_central': 'Visualizou a banca central',
    'admin_bancas': 'Visualizou as bancas',
    'admin_despachantes': 'Visualizou os despachantes',
    # Financeiro
    'financeiro:requisicao_lista': 'Visualizou as requisições de fundo',
    'financeiro:requisicao_criar': 'Visualizou o formulário de criação de requisição de fundo',
    'financeiro:requisicao_detalhe': 'Visualizou detalhes da requisição de fundo {nome}',
    'financeiro:requisicao_editar': 'Visualizou o formulário de edição da requisição de fundo {nome}',
    'financeiro:factura_lista': 'Visualizou as facturas',
    'financeiro:facturas_home': 'Visualizou as facturas',
    'financeiro:factura_detalhe': 'Visualizou detalhes da factura {nome}',
    'financeiro:factura_editar': 'Visualizou o formulário de edição da factura {nome}',
    'financeiro:recibo_lista': 'Visualizou os recibos',
    'financeiro:recibo_criar': 'Visualizou o formulário de criação de recibo',
    'financeiro:recibo_detalhe': 'Visualizou detalhes do recibo {nome}',
    'financeiro:recibo_editar': 'Visualizou o formulário de edição do recibo {nome}',
    'financeiro:nota_credito_lista': 'Visualizou as notas de crédito',
    'financeiro:nota_credito_criar': 'Visualizou o formulário de criação de nota de crédito',
    'financeiro:nota_credito_detalhe': 'Visualizou detalhes da nota de crédito {nome}',
    'financeiro:nota_credito_editar': 'Visualizou o formulário de edição da nota de crédito {nome}',
    'financeiro:nota_debito_lista': 'Visualizou as notas de débito',
    'financeiro:nota_debito_criar': 'Visualizou o formulário de criação de nota de débito',
    'financeiro:nota_debito_detalhe': 'Visualizou detalhes da nota de débito {nome}',
    'financeiro:nota_debito_editar': 'Visualizou o formulário de edição da nota de débito {nome}',
    'financeiro:factura_recibo_lista': 'Visualizou as facturas-recibo',
    'financeiro:factura_recibo_detalhe': 'Visualizou detalhes da factura-recibo {nome}',
    'financeiro:factura_recibo_editar': 'Visualizou o formulário de edição da factura-recibo {nome}',
    'financeiro:notas_home': 'Visualizou as notas',
    'financeiro:conta_corrente_home': 'Visualizou o conta corrente',
    'financeiro:relatorio_home': 'Visualizou os relatórios financeiros',
    # Utilizadores / Sistema
    'dashboard': 'Visualizou o dashboard principal',
    'dashboard_colaborador': 'Visualizou o dashboard do colaborador',
    'colaborador_perfil': 'Visualizou o seu perfil',
    'colaborador_documentos': 'Visualizou os seus documentos',
    'colaborador_presenca': 'Visualizou o seu controlo de presença',
    'colaborador_salario': 'Visualizou o seu processo salarial',
    'colaborador_historico_salarial': 'Visualizou o seu histórico salarial',
    'colaborador_ferias': 'Visualizou as suas férias',
    'colaborador_buscar': 'Pesquisou no sistema',
    'meu_perfil': 'Visualizou o seu perfil',
    'funcoes_lista': 'Visualizou as funções',
    'funcao_novo': 'Visualizou o formulário de criação de função',
    'funcao_editar': 'Visualizou o formulário de edição da função {nome}',
    'funcao_permissoes': 'Visualizou as permissões da função {nome}',
    'logs_atividade': 'Visualizou os logs de actividade',
    'manual_utilizador': 'Visualizou o manual do utilizador',
}

# Descrições legíveis para visualizações de páginas (GET) — fallback por path
_DESCOES_VIEW = {
    '/dashboard/': 'Visualizou o dashboard principal',
    '/rh/presencas/': 'Visualizou o controlo de presenças',
    '/rh/ferias/': 'Visualizou o mapa de férias',
    '/rh/colaboradores/': 'Visualizou a lista de colaboradores',
    '/rh/recrutamento/': 'Visualizou as vagas de emprego',
    '/rh/avaliacoes/': 'Visualizou as avaliações de desempenho',
    '/rh/salarios/': 'Visualizou o processamento salarial',
    '/rh/subsidios/': 'Visualizou os subsídios',
    '/rh/cargos/': 'Visualizou os cargos da banca',
    '/rh/banca/': 'Visualizou a banca',
    '/financeiro/facturas/': 'Visualizou as facturas',
    '/financeiro/recibos/': 'Visualizou os recibos',
    '/financeiro/notas-credito/': 'Visualizou as notas de crédito',
    '/financeiro/notas-debito/': 'Visualizou as notas de débito',
    '/financeiro/requisicoes/': 'Visualizou as requisições de fundo',
    '/governanca/': 'Visualizou o módulo de governança',
    '/du/lista/': 'Visualizou as declarações únicas',
    '/logs/': 'Visualizou os logs de actividade',
    '/relatorios/': 'Visualizou os relatórios',
}

# Padrões regex para páginas com ID específico (GET) — fallback
_DESCOES_VIEW_REGEX = [
    (r'^/du/[^/]+/ver/$', 'Visualizou detalhes de uma declaração única'),
    (r'^/du/[^/]+/historico/$', 'Visualizou o histórico de uma declaração única'),
    (r'^/financeiro/requisicoes/\d+/$', 'Visualizou detalhes de uma requisição de fundo'),
    (r'^/rh/recrutamento/\d+/$', 'Visualizou detalhes de uma vaga'),
    (r'^/rh/recrutamento/candidatura/\d+/$', 'Visualizou detalhes de uma candidatura'),
]

# Mapeamento de padrões de URL para descrições de acções POST — fallback
_POST_DESCOES = [
    # RH — Presenças e Férias
    (r'/rh/presencas/registar/', 'CREATE', 'Registou uma presença'),
    (r'/rh/presencas/aprovar-massa/', 'APPROVE', 'Aprovou presenças em massa'),
    (r'/rh/presencas/\d+/aprovar/', 'APPROVE', 'Aprovou um registo de presença'),
    (r'/rh/presencas/\d+/apagar/', 'DELETE', 'Removeu um registo de presença'),
    (r'/rh/ferias/pedir/', 'CREATE', 'Submeteu um pedido de férias'),
    (r'/rh/ferias/\d+/aprovar/', 'APPROVE', 'Aprovou um pedido de férias'),
    (r'/rh/ferias/\d+/apagar/', 'DELETE', 'Removeu um pedido de férias'),

    # RH — Colaboradores / Bancas / Filiais
    (r'/rh/colaboradores/novo/', 'CREATE', 'Cadastrou um novo colaborador'),
    (r'/rh/colaboradores/\d+/editar/', 'EDIT', 'Editou dados do colaborador'),
    (r'/rh/colaboradores/\d+/apagar/', 'DELETE', 'Removeu um colaborador'),
    (r'/rh/colaboradores/\d+/reenviar-email/', 'SEND_EMAIL', 'Reenviou credenciais ao colaborador'),
    (r'/rh/colaboradores/\d+/cargo/', 'EDIT', 'Alterou o cargo do colaborador'),
    (r'/rh/banca/criar/', 'CREATE', 'Criou a banca'),
    (r'/rh/banca/editar/', 'EDIT', 'Editou a banca'),
    (r'/rh/filiais/nova/', 'CREATE', 'Criou uma nova filial'),
    (r'/rh/filiais/\d+/editar/', 'EDIT', 'Editou uma filial'),
    (r'/rh/filiais/\d+/apagar/', 'DELETE', 'Eliminou uma filial'),
    (r'/rh/filiais/\d+/responsavel/novo/', 'CREATE', 'Atribuiu um responsável à filial'),

    # RH — Cargos / Subsídios / Salários / Vagas
    (r'/rh/cargos/novo/', 'CREATE', 'Criou um novo cargo'),
    (r'/rh/cargos/\d+/editar/', 'EDIT', 'Editou um cargo'),
    (r'/rh/cargos/\d+/eliminar/', 'DELETE', 'Eliminou um cargo'),
    (r'/rh/subsidios/novo/', 'CREATE', 'Criou um novo subsídio'),
    (r'/rh/subsidios/\d+/editar/', 'EDIT', 'Editou um subsídio'),
    (r'/rh/subsidios/\d+/apagar/', 'DELETE', 'Eliminou um subsídio'),
    (r'/rh/salarios/novo/', 'CREATE', 'Criou um processamento salarial'),
    (r'/rh/salarios/\d+/apagar/', 'DELETE', 'Eliminou um processamento salarial'),
    (r'/rh/recrutamento/nova/', 'CREATE', 'Criou uma nova vaga de emprego'),
    (r'/rh/recrutamento/\d+/editar/', 'EDIT', 'Editou uma vaga de emprego'),
    (r'/rh/recrutamento/\d+/eliminar/', 'DELETE', 'Eliminou uma vaga'),
    (r'/rh/recrutamento/candidatura/\d+/estado/', 'EDIT', 'Alterou o estado de uma candidatura'),
    (r'/rh/recrutamento/candidatura/\d+/entrevista/nova/', 'CREATE', 'Criou uma entrevista'),
    (r'/rh/recrutamento/entrevista/\d+/resultado/', 'EDIT', 'Registou o resultado da entrevista'),
    (r'/rh/recrutamento/candidatura/\d+/integracao/nova/', 'CREATE', 'Criou um plano de integração'),

    # RH — Avaliações
    (r'/rh/avaliacoes/ciclo/novo/', 'CREATE', 'Criou um ciclo de avaliação'),
    (r'/rh/avaliacoes/ciclo/\d+/editar/', 'EDIT', 'Editou um ciclo de avaliação'),
    (r'/rh/avaliacoes/ciclo/\d+/apagar/', 'DELETE', 'Eliminou um ciclo de avaliação'),
    (r'/rh/avaliacoes/ciclo/\d+/avaliar/\d+/apagar/', 'DELETE', 'Eliminou uma avaliação'),

    # RH — Institucional
    (r'/rh/institucional/subsidios/novo/', 'CREATE', 'Criou um novo subsídio'),
    (r'/rh/institucional/subsidios/\d+/editar/', 'EDIT', 'Editou um subsídio'),
    (r'/rh/institucional/subsidios/\d+/apagar/', 'DELETE', 'Eliminou um subsídio'),
    (r'/rh/institucional/salarios/novo/', 'CREATE', 'Criou um processamento salarial'),
    (r'/rh/institucional/salarios/\d+/apagar/', 'DELETE', 'Eliminou um processamento salarial'),
    (r'/rh/institucional/recrutamento/nova/', 'CREATE', 'Criou uma nova vaga de emprego'),
    (r'/rh/institucional/recrutamento/\d+/editar/', 'EDIT', 'Editou uma vaga de emprego'),
    (r'/rh/institucional/recrutamento/\d+/eliminar/', 'DELETE', 'Eliminou uma vaga'),
    (r'/rh/institucional/presencas/registar/', 'CREATE', 'Registou uma presença'),
    (r'/rh/institucional/presencas/\d+/aprovar/', 'APPROVE', 'Aprovou um registo de presença'),
    (r'/rh/institucional/presencas/\d+/apagar/', 'DELETE', 'Removeu um registo de presença'),
    (r'/rh/institucional/ferias/pedir/', 'CREATE', 'Submeteu um pedido de férias'),
    (r'/rh/institucional/ferias/\d+/aprovar/', 'APPROVE', 'Aprovou um pedido de férias'),
    (r'/rh/institucional/ferias/\d+/apagar/', 'DELETE', 'Removeu um pedido de férias'),
    (r'/rh/institucional/avaliacoes/ciclo/novo/', 'CREATE', 'Criou um ciclo de avaliação'),
    (r'/rh/institucional/avaliacoes/ciclo/\d+/avaliar/\d+/apagar/', 'DELETE', 'Eliminou uma avaliação'),

    # RH — Admin
    (r'/rh/admin/despachantes/novo/', 'CREATE', 'Criou um novo despachante'),
    (r'/rh/admin/despachantes/\d+/editar/', 'EDIT', 'Editou um despachante'),
    (r'/rh/admin/despachantes/\d+/toggle/', 'EDIT', 'Alterou o estado de um despachante'),
    (r'/rh/admin/despachantes/\d+/enviar-credenciais/', 'SEND_EMAIL', 'Reenviou credenciais ao despachante'),
    (r'/rh/admin/despachantes/\d+/cargo/', 'EDIT', 'Atribuiu cargo ao despachante'),
    (r'/rh/admin/bancas/\d+/toggle/', 'EDIT', 'Alterou o estado de uma banca'),
    (r'/rh/banca-central/criar/', 'CREATE', 'Criou a banca central'),
    (r'/rh/banca-central/editar/', 'EDIT', 'Editou a banca central'),

    # Clientes
    (r'/clientes/criar/', 'CREATE', 'Cadastrou um novo cliente'),
    (r'/clientes/\d+/editar/', 'EDIT', 'Editou dados do cliente'),
    (r'/clientes/\d+/excluir/', 'DELETE', 'Removeu um cliente'),

    # Financeiro — Requisições de Fundo
    (r'/financeiro/requisicoes/criar/', 'CREATE', 'Criou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/editar/', 'EDIT', 'Editou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/cancelar/', 'CANCEL', 'Cancelou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/eliminar/', 'DELETE', 'Eliminou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/aceitar/', 'APPROVE', 'Aprovou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/rejeitar/', 'REJECT', 'Rejeitou uma requisição de fundo'),
    (r'/financeiro/requisicoes/\d+/criar-factura/', 'CREATE', 'Criou uma factura a partir da requisição'),
    (r'/financeiro/requisicoes/\d+/criar-factura-recibo/', 'CREATE', 'Criou uma factura-recibo a partir da requisição'),
    (r'/financeiro/requisicoes/\d+/linha/adicionar/', 'CREATE', 'Adicionou uma linha à requisição'),
    (r'/financeiro/requisicoes/\d+/linha/\d+/editar/', 'EDIT', 'Editou uma linha da requisição'),
    (r'/financeiro/requisicoes/\d+/linha/\d+/eliminar/', 'DELETE', 'Eliminou uma linha da requisição'),
    (r'/financeiro/requisicoes/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou a requisição por email'),
    (r'/financeiro/requisicoes/\d+/pdf/', 'EXPORT', 'Exportou a requisição em PDF'),

    # Financeiro — Facturas
    (r'/financeiro/facturas/\d+/editar/', 'EDIT', 'Editou uma factura'),
    (r'/financeiro/facturas/\d+/cancelar/', 'CANCEL', 'Cancelou uma factura'),
    (r'/financeiro/facturas/\d+/eliminar/', 'DELETE', 'Eliminou uma factura'),
    (r'/financeiro/facturas/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou factura por email'),
    (r'/financeiro/facturas/\d+/pdf/', 'EXPORT', 'Exportou factura em PDF'),

    # Financeiro — Recibos
    (r'/financeiro/recibos/criar/', 'CREATE', 'Emitiu um novo recibo'),
    (r'/financeiro/recibos/\d+/editar/', 'EDIT', 'Editou um recibo'),
    (r'/financeiro/recibos/\d+/cancelar/', 'CANCEL', 'Cancelou um recibo'),
    (r'/financeiro/recibos/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou recibo por email'),
    (r'/financeiro/recibos/\d+/pdf/', 'EXPORT', 'Exportou recibo em PDF'),

    # Financeiro — Notas de Crédito / Débito
    (r'/financeiro/notas-credito/criar/', 'CREATE', 'Criou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/editar/', 'EDIT', 'Editou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/aprovar/', 'APPROVE', 'Aprovou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/rejeitar/', 'REJECT', 'Rejeitou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/cancelar/', 'CANCEL', 'Cancelou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/eliminar/', 'DELETE', 'Eliminou uma nota de crédito'),
    (r'/financeiro/notas-credito/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou nota de crédito por email'),
    (r'/financeiro/notas-debito/criar/', 'CREATE', 'Criou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/editar/', 'EDIT', 'Editou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/aprovar/', 'APPROVE', 'Aprovou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/rejeitar/', 'REJECT', 'Rejeitou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/cancelar/', 'CANCEL', 'Cancelou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/eliminar/', 'DELETE', 'Eliminou uma nota de débito'),
    (r'/financeiro/notas-debito/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou nota de débito por email'),

    # Financeiro — Facturas-Recibo
    (r'/financeiro/facturas-recibo/\d+/editar/', 'EDIT', 'Editou uma factura-recibo'),
    (r'/financeiro/facturas-recibo/\d+/cancelar/', 'CANCEL', 'Cancelou uma factura-recibo'),
    (r'/financeiro/facturas-recibo/\d+/enviar-email/', 'SEND_EMAIL', 'Reenviou factura-recibo por email'),

    # Financeiro — Exportações
    (r'/financeiro/conta-corrente/mensal/excel/', 'EXPORT', 'Exportou a conta corrente mensal em Excel'),
    (r'/financeiro/conta-corrente/mensal/pdf/', 'EXPORT', 'Exportou a conta corrente mensal em PDF'),
    (r'/financeiro/conta-corrente/periodica/excel/', 'EXPORT', 'Exportou a conta corrente periódica em Excel'),
    (r'/financeiro/conta-corrente/periodica/pdf/', 'EXPORT', 'Exportou a conta corrente periódica em PDF'),
    (r'/financeiro/relatorios/[^/]+/pdf/', 'EXPORT', 'Exportou um relatório em PDF'),

    # Aduaneiro
    (r'/du/guardar/', 'CREATE', 'Guardou uma declaração única'),
    (r'/du/[^/]+/apagar/', 'DELETE', 'Eliminou uma declaração única'),
    (r'/du/[^/]+/status/', 'EDIT', 'Alterou o estado de uma declaração única'),
    (r'/du/api/criar-cliente/', 'CREATE', 'Criou um novo cliente'),

    # Utilizadores / Perfil
    (r'/users/funcoes/novo/', 'CREATE', 'Criou uma nova função'),
    (r'/users/funcoes/\d+/editar/', 'EDIT', 'Editou uma função'),
    (r'/users/funcoes/\d+/eliminar/', 'DELETE', 'Eliminou uma função'),
    (r'/perfil/guardar/', 'EDIT', 'Actualizou o seu perfil'),
    (r'/perfil/senha/', 'EDIT', 'Alterou a sua senha'),
    (r'/perfil/assinatura/', 'EDIT', 'Actualizou a sua assinatura'),
    (r'/perfil/foto/remover/', 'EDIT', 'Removeu a sua foto de perfil'),
]

# Descrição genérica para POST sem pattern específico
_POST_FALLBACK = {
    'CREATE': 'Criou um registo em {modulo}',
    'EDIT': 'Editou um registo em {modulo}',
    'DELETE': 'Removeu um registo em {modulo}',
    'APPROVE': 'Aprovou um registo em {modulo}',
    'REJECT': 'Rejeitou um registo em {modulo}',
    'CANCEL': 'Cancelou um registo em {modulo}',
    'SEND_EMAIL': 'Enviou um email',
    'EXPORT': 'Exportou dados',
}


# ────────────────────────────────────────────────────────────────────────────
# Helpers de resolução de nomes
# ────────────────────────────────────────────────────────────────────────────

def _importar_modelo(caminho):
    """Importa um modelo a partir de 'app.models.Nome'."""
    try:
        app, _, resto = caminho.partition('.models.')
        if not app or not resto:
            return None
        modulo = __import__('%s.models' % app, fromlist=[resto])
        return getattr(modulo, resto, None)
    except Exception:
        return None


def _obter_objeto(caminho_modelo, kw, valor):
    """Busca um registo pelo kwarg do URL. Devolve None em caso de falha."""
    Modelo = _importar_modelo(caminho_modelo)
    if Modelo is None:
        return None
    try:
        return Modelo.objects.get(**{kw: valor})
    except Exception:
        return None


def _json_body(request):
    """Lê o corpo JSON do pedido (cacheado pelo Django; a view pode reler)."""
    try:
        if not request.body:
            return None
        return json.loads(request.body)
    except Exception:
        return None


def _label_de_caminho(caminho):
    """'clientes.models.Cliente' → 'clientes.Cliente'."""
    app, _, resto = caminho.partition('.models.')
    return '%s.%s' % (app, resto) if app and resto else ''


def _nome_do_registo(request, match, reg):
    """
    Obtém (nome, objeto) para um POST.
    Prioridade: objeto do URL → payload JSON → campos POST → FKs do POST.
    """
    if reg.get('kw'):
        valor = match.kwargs.get(reg['kw'])
        if valor is not None:
            obj = _obter_objeto(reg['modelo'], reg['kw'], valor)
            if obj is not None:
                return str(obj)[:80], obj

    if reg.get('json'):
        payload = _json_body(request)
        if payload:
            for campo in reg.get('json_campos', ()) or ():
                v = payload.get(campo)
                if v and str(v).strip():
                    return str(v).strip()[:80], None

    for campo, modelo_fk in (reg.get('post_fk') or {}).items():
        v = request.POST.get(campo)
        if v and str(v).strip().isdigit():
            obj = _obter_objeto(modelo_fk, 'pk', int(v))
            if obj is not None:
                return str(obj)[:80], None

    if reg.get('post_join'):
        valores = []
        for campo in reg.get('post_join') or ():
            v = request.POST.get(campo)
            if v and v.strip():
                valores.append(v.strip())
        if valores:
            return '/'.join(valores)[:80], None

    for campo in reg.get('post', ()) or ():
        v = request.POST.get(campo)
        if v and v.strip():
            return v.strip()[:80], None

    return None, None


def _resolver_registo_post(request):
    """Devolve (accao, descricao, modelo_alvo, id_alvo, detalhes) ou None."""
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return None

    chave = '%s:%s' % (match.app_name, match.url_name) if match.app_name else match.url_name

    # DU é guardada via AJAX JSON — create/edit distingue-se pelo 'uuid' no payload
    if chave == 'aduaneiro:du_guardar':
        return _registo_du_guardar(request)

    reg = _REGISTO_ENTIDADES.get(chave)
    if not reg:
        return None

    nome, obj = _nome_do_registo(request, match, reg)
    if not nome:
        return (reg['accao'], reg['geral'], '', None, None)

    modelo_alvo = obj._meta.label if obj is not None else _label_de_caminho(reg.get('modelo', ''))
    id_alvo = obj.pk if obj is not None else None
    detalhes = {'nome': nome}
    descricao = reg['template'].format(nome=nome)
    return (reg['accao'], descricao, modelo_alvo, id_alvo, detalhes)


def _registo_du_guardar(request):
    """Guarda/actualiza DU via JSON: payload['uuid'] presente → edição."""
    payload = _json_body(request)
    if not payload:
        return None
    du_uuid = payload.get('uuid')
    if du_uuid:
        du = _obter_objeto('aduaneiro.models.DeclaracaoUnica', 'du_uuid', du_uuid)
        if du is None:
            return ('EDIT', 'Editou uma DU', 'aduaneiro.DeclaracaoUnica', None, None)
        nome = str(du)[:80]
        return ('EDIT', 'Editou a DU %s' % nome, 'aduaneiro.DeclaracaoUnica', du.pk, {'nome': nome})

    dados = payload.get('dados') or {}
    nome = ''
    for campo in ('exportador_nome', 'destinatario_nome', 'cliente_nome'):
        v = str(dados.get(campo) or '').strip()
        if v:
            nome = v[:80]
            break
    if nome:
        return ('CREATE', 'Criou uma nova DU — %s' % nome, 'aduaneiro.DeclaracaoUnica', None, {'nome': nome})
    return ('CREATE', 'Criou uma nova DU', 'aduaneiro.DeclaracaoUnica', None, None)


class ActivityLogMiddleware:
    """
    Middleware que regista automaticamente as acções dos utilizadores no LogAtividade.
    Regista VIEW em páginas GET e acções específicas (com nome da entidade) em POST.
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
        metodo = request.method

        if metodo == 'GET':
            self._log_view(request)
        elif metodo == 'POST':
            self._log_post(request)

    def _log_view(self, request):
        """Regista visualização de página com descrição legível e nome da entidade."""
        path = request.path
        # Ignorar AJAX e requisições internas
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return
        if '/api/' in path:
            return

        from .models import registrar_log
        modulo = getattr(request, '_log_modulo', 'sistema')

        descricao = None
        modelo_alvo = ''
        id_alvo = None
        detalhes = None

        try:
            match = resolve(request.path_info)
            chave = '%s:%s' % (match.app_name, match.url_name) if match.app_name else match.url_name
        except Resolver404:
            chave = None

        if chave and chave in _DESCOES_VIEW_POR_VIEW:
            tpl = _DESCOES_VIEW_POR_VIEW[chave]
            if '{nome}' in tpl:
                alvo = _ALVO_VIEW.get(chave)
                obj = None
                if alvo:
                    modelo, kw = alvo
                    obj = _obter_objeto(modelo, kw, match.kwargs.get(kw))
                if obj is None:
                    chave = None  # sem objeto → cai nas tabelas por path
                else:
                    nome = str(obj)[:80]
                    descricao = tpl.format(nome=nome)
                    modelo_alvo = obj._meta.label
                    id_alvo = obj.pk
                    detalhes = {'nome': nome}
            else:
                descricao = tpl

        if not descricao:
            # Fallback por path
            descricao = _DESCOES_VIEW.get(path)
            if not descricao:
                for pattern, d in _DESCOES_VIEW_REGEX:
                    if re.search(pattern, path):
                        descricao = d
                        break

        if not descricao:
            nome_modulo = _MODULO_NOMES.get(modulo, 'Sistema')
            descricao = 'Visualizou página de %s' % nome_modulo

        registrar_log(request, 'VIEW', modulo, descricao,
                      modelo_alvo=modelo_alvo, id_alvo=id_alvo, detalhes=detalhes)

    def _log_post(self, request):
        """Regista acções POST com descrição específica (com nome da entidade)."""
        from .models import registrar_log
        modulo = getattr(request, '_log_modulo', 'sistema')

        # 1) Descrição detalhada via registo de entidades (resolve por url_name)
        resultado = _resolver_registo_post(request)
        if resultado:
            accao, descricao, modelo_alvo, id_alvo, detalhes = resultado
            registrar_log(request, accao, modulo, descricao,
                          modelo_alvo=modelo_alvo, id_alvo=id_alvo, detalhes=detalhes)
            return

        # 2) Fallback: patterns específicos por path
        path = request.path
        accao = None
        descricao = None
        for pattern, accao_pt, desc in _POST_DESCOES:
            if re.search(pattern, path):
                accao = accao_pt
                descricao = desc
                break

        if not accao:
            # 3) Fallback: detetar acção por palavras-chave no path
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

            descricao = _POST_FALLBACK.get(accao, '%s — %s' % (accao, path)).format(
                modulo=_MODULO_NOMES.get(modulo, modulo))

        registrar_log(request, accao, modulo, descricao)
