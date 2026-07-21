"""Views do módulo users — autenticação, dashboards e portal do colaborador."""
# pylint: disable=no-member
import json
import logging
import re
import smtplib
import ssl as ssl_lib
from datetime import date

import bcrypt
import requests
from utils.ssl_utils import requests_kwargs_ssl
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from rh.models import (
    Colaborador,
    DocumentoColaborador,
    PedidoFerias,
    ReciboSalarial,
    RegistoPresenca,
)

from .auth_decorators import (
    criar_sessao_usuario,
    limpar_sessao,
    requer_sessao_ativa,
    sessao_expirada,
    tempo_restante_sessao,
)
from .models import (
    ColaboradorInstitucional,
    FeriasInstitucional,
    Funcao,
    PresencaInstitucional,
    ReciboSalarialInstitucional,
    Usuario,
)

login_logger = logging.getLogger('users.login')


# ─── Helpers de password ──────────────────────────────────────────────────────

def _verificar_password(senha: str, hash_armazenado: str) -> bool:
    """Verifica senha contra hash bcrypt ($2y$ PHP ou $2b$ Python)."""
    if not hash_armazenado:
        return False
    try:
        hash_bytes = hash_armazenado.replace("$2y$", "$2b$").encode("utf-8")
        return bcrypt.checkpw(senha.encode("utf-8"), hash_bytes)
    except Exception:  # noqa: BLE001
        return False


def _hash_password(senha: str) -> str:
    """Gera hash bcrypt compatível com PHP ($2y$)."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(senha.encode("utf-8"), salt)
    return hashed.decode("utf-8").replace("$2b$", "$2y$")


# ─── Helper de sessão do colaborador ─────────────────────────────────────────

def _verificar_sessao_colaborador(request):
    """Verifica sessão activa de colaborador. Retorna (colaborador, None) ou (None, redirect)."""
    if not request.session.get("usuario_id"):
        return None, redirect("login")
    if sessao_expirada(request):
        limpar_sessao(request)
        return None, redirect("login")
    if request.session.get("tipo_usuario") != "colaborador":
        return None, redirect("login")
    colaborador_id = request.session.get("colaborador_id")
    if not colaborador_id:
        return None, None  # pode ser institucional sem colaborador banca
    try:
        return Colaborador.objects.select_related('cargo_banca', 'filial').get(id=colaborador_id), None
    except Colaborador.DoesNotExist:
        return None, redirect("login")


def _get_institucional(request):
    """Retorna ColaboradorInstitucional ligado ao usuário da sessão.

    Se não existir registo mas o utilizador for Colaborador Institucional,
    cria automaticamente um registo básico para poder aceder às funcionalidades.
    """
    from .models import ColaboradorInstitucional, Usuario
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        return None
    try:
        return ColaboradorInstitucional.objects.get(usuario_id=usuario_id)
    except ColaboradorInstitucional.DoesNotExist:
        usuario = Usuario.objects.filter(pk=usuario_id).first()
        if not usuario or usuario.papel != "Colaborador Institucional":
            return None
        return ColaboradorInstitucional.objects.create(
            usuario=usuario,
            nome=usuario.nome,
            email=usuario.email or "",
            area_actuacao="",
            estado="Ativo",
        )


# ─── Autenticação ─────────────────────────────────────────────────────────────

def login_view(request):
    """Página de login — autentica utilizadores e colaboradores."""
    def _get_ip():
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '-')

    ip = _get_ip()

    if request.session.get("usuario_id"):
        if not sessao_expirada(request):
            login_logger.info('Sessao ativa detectada, redirecionando para dashboard: usuario_id=%s ip=%s',
                              request.session.get("usuario_id"), ip)
            return redirect("dashboard")
        login_logger.info('Sessao expirada detectada ao verificar login existente: usuario_id=%s ip=%s',
                          request.session.get("usuario_id"), ip)
        limpar_sessao(request)

    if request.method != "POST":
        return render(request, "login.html")

    email = request.POST.get("email", "").strip().lower()
    senha = request.POST.get("password", "").strip()

    login_logger.info('Tentativa de login: email=%s ip=%s method=POST', email, ip)

    if not email or not senha:
        login_logger.warning('Login falhou — campos vazios: email=%s ip=%s', email, ip)
        messages.error(request, "Preencha todos os campos.")
        return render(request, "login.html")

    # ── Brute-force protection ──────────────────────────────────────────
    lockout_key = f"login_lockout:{email}"
    if cache.get(lockout_key):
        login_logger.warning('Login bloqueado (brute-force): email=%s ip=%s', email, ip)
        messages.error(request, "Conta bloqueada temporariamente. Tente novamente em 15 minutos.")
        return render(request, "login.html")

    attempts_key = f"login_attempts:{email}"
    max_attempts = 5
    lockout_timeout = 15 * 60  # 15 minutes in seconds

    usuario = None
    tipo_usuario = None
    usuario_bloqueado = False

    # 1. Tentar na tabela usuarios
    try:
        u = Usuario.objects.get(email=email)
        login_logger.debug('Usuario encontrado na tabela usuarios: email=%s status=%s', email, u.status)
        
        # Verificar se está bloqueado
        if u.status == 'Suspenso':
            usuario_bloqueado = True
            login_logger.warning('Login falhou — conta suspensa: email=%s ip=%s', email, ip)
            from .models import registrar_log
            registrar_log(request, 'LOGIN_FALHA', 'users',
                          f"Tentativa de login com conta suspensa: {email}",
                          email_forcado=email)
            messages.error(
                request,
                "A sua conta encontra-se suspensa. Entre em contacto com o seu responsável."
            )
            return render(request, "login.html")
        
        # Verificar se está inativo
        if u.status == 'Inativo':
            login_logger.warning('Login falhou — conta inativa: email=%s ip=%s', email, ip)
            from .models import registrar_log
            registrar_log(request, 'LOGIN_FALHA', 'users',
                          f"Tentativa de login com conta inativa: {email}",
                          email_forcado=email)
            messages.error(
                request,
                "A sua conta encontra-se inativa. Entre em contacto com o seu responsável."
            )
            return render(request, "login.html")
        
        # Verificar senha apenas se status='Ativo'
        if u.status == "Ativo" and _verificar_password(senha, u.password):
            usuario = u
            tipo_usuario = "usuario"
            login_logger.info('Credenciais validadas na tabela usuarios: email=%s', email)
    except Usuario.DoesNotExist:
        login_logger.debug('Usuario NAO encontrado na tabela usuarios: email=%s', email)
    except Exception as e:
        login_logger.error('Erro ao consultar tabela usuarios: email=%s erro=%s', email, str(e), exc_info=True)

    # 2. Tentar na tabela colaboradores
    if not usuario and not usuario_bloqueado:
        try:
            col = Colaborador.objects.select_related('cargo_banca').prefetch_related('cargo_banca__permissoes').get(email=email, estado="Ativo")
            login_logger.debug('Colaborador encontrado: email=%s nome=%s', email, col.nome)
            if col.password and _verificar_password(senha, col.password):
                tipo_usuario = "colaborador"
                login_logger.info('Credenciais validadas na tabela colaboradores: email=%s', email)

                class _UsuarioColaborador:  # noqa: R0903
                    def __init__(self, c):
                        self.id = c.id
                        self.nome = c.nome
                        self.email = c.email
                        self.nif = c.nif
                        self.cedula = c.bi
                        self.telefone = c.telefone
                        self.username = c.email
                        self.tipo = "colaborador"
                        self.colaborador_id = c.id
                        self.is_secretario = False
                        self.is_vice_secretario = False
                        self.funcao = None
                        self.banca_usuario_id = c.banca.usuario_id if c.banca else None
                        self.banca_id = c.banca_id
                        # cargo_banca
                        if c.cargo_banca_id:
                            try:
                                self.cargo_banca_id = c.cargo_banca_id
                                self.cargo_banca_nome = c.cargo_banca.nome
                                self.papel = "Colaborador"
                                self.papel_display = c.cargo_banca.nome
                                self._permissoes = list(
                                    c.cargo_banca.permissoes.values_list('codigo', flat=True)
                                )
                            except Exception:
                                self.cargo_banca_id = c.cargo_banca_id
                                self.cargo_banca_nome = ''
                                self.papel = "Colaborador"
                                self.papel_display = "Colaborador"
                                self._permissoes = []
                        else:
                            self.cargo_banca_id = None
                            self.cargo_banca_nome = ''
                            self.papel = "Colaborador"
                            self.papel_display = "Colaborador"
                            self._permissoes = []

                usuario = _UsuarioColaborador(col)
        except Colaborador.DoesNotExist:
            login_logger.debug('Colaborador NAO encontrado: email=%s', email)
        except Exception as e:
            login_logger.error('Erro ao consultar tabela colaboradores: email=%s erro=%s', email, str(e), exc_info=True)

    if not usuario:
        login_logger.warning('Login falhou — credenciais invalidas: email=%s ip=%s', email, ip)
        from .models import registrar_log
        registrar_log(request, 'LOGIN_FALHA', 'users',
                      f"Tentativa de login falhada: {email}",
                      email_forcado=email)

        attempts = cache.get(attempts_key, 0) + 1
        if attempts >= max_attempts:
            cache.set(lockout_key, True, lockout_timeout)
            cache.delete(attempts_key)
            messages.error(request, "Conta bloqueada temporariamente. Tente novamente em 15 minutos.")
        else:
            cache.set(attempts_key, attempts, lockout_timeout)
            remaining = max_attempts - attempts
            messages.error(request, f"❌ Credenciais inválidas. Verifique o seu email e senha. ({remaining} tentativa(s) restante(s))")
        return render(request, "login.html")

    # ── Colaborador Institucional sem função → modo limitado (como colaborador banca) ──
    institucional_sem_funcao = (
        tipo_usuario == 'usuario' and usuario.papel == 'Colaborador Institucional'
        and not usuario.funcao_id
    )
    if institucional_sem_funcao:
        from .models import registrar_log
        registrar_log(request, 'LOGIN_SEM_FUNCAO', 'users',
                      f"Login de colaborador institucional sem função: {email}",
                      email_forcado=email)

    if institucional_sem_funcao:
        from .models import registrar_log as _rl
        criar_sessao_usuario(request, usuario)
        cache.delete(attempts_key)
        # Manter sessão de colaborador institucional (preservar papel real)
        request.session['tipo_usuario'] = 'colaborador'
        request.session['usuario'] = {
            **request.session['usuario'],
            'papel': 'Colaborador Institucional',
            'papel_display': 'Colaborador Institucional',
            'permissoes': [],
            'funcao_nome': '',
        }
        login_logger.info('LOGIN_SUCESSO (institucional limitado): nome=%s email=%s tipo=%s ip=%s',
                          usuario.nome, usuario.email, tipo_usuario, ip)
        _rl(request, 'LOGIN', 'users',
            f"Login limitado de colaborador institucional sem função: {usuario.nome} ({usuario.email})")
        messages.success(
            request,
            f"Bem-vindo(a) {usuario.nome}! O seu acesso é limitado porque ainda não tem uma Função atribuída. Contacte o administrador para obter mais permissões."
        )
        return redirect("dashboard_colaborador")

    criar_sessao_usuario(request, usuario)
    cache.delete(attempts_key)

    if tipo_usuario == "usuario":
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET ultimo_acesso = %s WHERE id = %s",
                [timezone.now(), usuario.id],
            )

    login_logger.info('LOGIN_SUCESSO: nome=%s email=%s tipo=%s usuario_id=%s ip=%s',
                      usuario.nome, usuario.email, tipo_usuario, usuario.id, ip)

    from .models import registrar_log
    registrar_log(request, 'LOGIN', 'users',
                  f"Login bem-sucedido: {usuario.nome} ({usuario.email})")

    messages.success(request, f"Bem-vindo(a) {usuario.nome}!")
    if tipo_usuario == "colaborador":
        return redirect("dashboard_colaborador")
    return redirect("dashboard")


@require_http_methods(["POST"])
def login_portal_view(request):
    """
    Autentica usuário via portal externo e cria/atualiza usuário local.
    
    Fluxo:
    1. Recebe credenciais do modal (email, password)
    2. Envia para o endpoint do portal: https://portal.cdoangola.co.ao/controllers/sicdoa.php
    3. Se credenciais inválidas: retorna erro
    4. Se credenciais válidas:
       - Verifica se usuário existe no SICDOA (por email)
       - Se não existe: cria novo usuário
       - Se existe: atualiza dados
       - Retorna credenciais para auto-login
    """
    try:
        # Parse JSON body
        data = json.loads(request.body)
        email = data.get('email', '').strip().lower()
        password = data.get('password', '').strip()
        
        if not email or not password:
            return JsonResponse({
                'success': False,
                'message': 'Email e senha são obrigatórios.'
            }, status=400)
        
        # Enviar credenciais para o portal
        portal_url = 'https://portal.cdoangola.co.ao/controllers/sicdoa.php'
        portal_payload = {
            'email': email,
            'password': password
        }
        
        try:
            portal_response = requests.post(
                portal_url,
                json=portal_payload,
                timeout=10,
                headers={'Content-Type': 'application/json'},
                **requests_kwargs_ssl(),
            )
            
            # Verificar se a resposta foi bem-sucedida
            if portal_response.status_code != 200:
                return JsonResponse({
                    'success': False,
                    'message': 'Credenciais inválidas do portal.'
                }, status=401)
            
            portal_data = portal_response.json()
            
            # Verificar se o status é 200 (sucesso)
            if portal_data.get('status') != 200:
                return JsonResponse({
                    'success': False,
                    'message': 'Credenciais inválidas do portal.'
                }, status=401)
            
        except requests.exceptions.Timeout:
            return JsonResponse({
                'success': False,
                'message': 'Tempo esgotado ao conectar com o portal. Tente novamente.'
            }, status=504)
        except requests.exceptions.RequestException as e:
            return JsonResponse({
                'success': False,
                'message': f'Erro ao conectar com o portal: {str(e)}'
            }, status=503)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'message': 'Resposta inválida do portal.'
            }, status=502)
        
        # Extrair dados do usuário do portal
        user_data = portal_data.get('users', {})
        people_data = portal_data.get('peoples', {})
        despachante_data = portal_data.get('despachantes', {})
        
        portal_id = user_data.get('id')
        portal_email = user_data.get('email', '').strip().lower()
        nome = people_data.get('name', '').strip()
        apelido = people_data.get('apelido', '').strip()
        telefone = people_data.get('telefone', '')
        nif = despachante_data.get('nif', '')
        cedula = despachante_data.get('cedula', '')
        
        # Nome completo
        nome_completo = f"{nome} {apelido}".strip() if apelido else nome
        
        # Verificar se usuário já existe no SICDOA
        try:
            usuario = Usuario.objects.get(email=portal_email)
            
            # Atualizar dados do usuário existente
            usuario.nome = nome_completo
            usuario.telefone = str(telefone) if telefone else usuario.telefone
            usuario.nif = nif if nif else usuario.nif
            usuario.cedula = cedula if cedula else usuario.cedula
            usuario.sso_portal_id = portal_id
            usuario.status = 'Ativo'
            usuario.save()
            
            # Criar sessão diretamente (não precisa de senha)
            criar_sessao_usuario(request, usuario)
            
            # Atualizar último acesso
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE usuarios SET ultimo_acesso = %s WHERE id = %s",
                    [timezone.now(), usuario.id],
                )
            
            # Retornar sucesso com flag de login direto
            return JsonResponse({
                'success': True,
                'message': 'Autenticação bem-sucedida!',
                'direct_login': True,  # Flag para redirecionar direto
                'user_id': usuario.id,
                'nome': usuario.nome
            })
            
        except Usuario.DoesNotExist:
            # Criar novo usuário SEM SENHA (password = NULL)
            # Gerar username único baseado no email
            username_base = portal_email.split('@')[0]
            username = username_base
            counter = 1
            
            while Usuario.objects.filter(username=username).exists():
                username = f"{username_base}{counter}"
                counter += 1
            
            usuario = Usuario.objects.create(
                username=username,
                password=None,  # SEM SENHA - usuário só pode logar via portal
                nome=nome_completo,
                email=portal_email,
                telefone=str(telefone) if telefone else '',
                nif=nif,
                cedula=cedula,
                papel='Despachante Oficial',
                status='Ativo',
                sso_portal_id=portal_id
            )
            
            # Criar sessão diretamente
            criar_sessao_usuario(request, usuario)
            
            # Atualizar último acesso
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE usuarios SET ultimo_acesso = %s WHERE id = %s",
                    [timezone.now(), usuario.id],
                )
            
            # Retornar sucesso com flag de login direto
            return JsonResponse({
                'success': True,
                'message': 'Autenticação bem-sucedida!',
                'direct_login': True,  # Flag para redirecionar direto
                'user_id': usuario.id,
                'nome': usuario.nome
            })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': 'Dados inválidos enviados.'
        }, status=400)
    except Exception as e:  # noqa: BLE001
        login_logger.error('LOGIN_PORTAL_ERRO: %s', e, exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Erro interno ao processar autenticação. Tente novamente.'
        }, status=500)


def logout_view(request):
    """Termina a sessão e redireciona para o login."""
    from .models import registrar_log
    usuario_nome = request.session.get('usuario', {}).get('nome', '')
    email = request.session.get('usuario', {}).get('email', '')
    registrar_log(request, 'LOGOUT', 'users',
                  f"Logout: {usuario_nome} ({email})")
    limpar_sessao(request)
    messages.info(request, "Sessão terminada com sucesso. Até logo!")
    return redirect("login")


# ─── Dashboards ───────────────────────────────────────────────────────────────

def dashboard_view(request):
    """Dashboard principal para utilizadores do sistema."""
    import sys, traceback, logging
    _log = logging.getLogger(__name__)
    if not request.session.get("usuario_id"):
        return redirect("login")
    if sessao_expirada(request):
        limpar_sessao(request)
        return redirect("login")
    try:
        return _dashboard_inner(request)
    except Exception:
        _log.exception("ERRO NO DASHBOARD")
        if not settings.DEBUG:
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
            from django.http import HttpResponseServerError
            return HttpResponseServerError(content)
        raise


def _dashboard_inner(request):

    usuario = request.session.get("usuario", {})
    uid     = request.session.get("usuario_id")
    papel   = usuario.get("papel", "")

    from aduaneiro.models import DeclaracaoUnica
    from clientes.models import Cliente
    from financeiro.models import FacturaCliente, ReciboCliente, NotaCredito, NotaDebito, FacturaRecibo
    from governanca.models import Notificacao
    from rh.models import Banca
    from django.utils import timezone as tz
    from django.db.models import Sum, Q
    from .permissoes import get_usuario_permissoes, _is_admin_ou_acesso_total

    # ── Mês actual (range UTC para evitar CONVERT_TZ com MySQL) ──────────
    _ms = tz.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _me = _ms.replace(year=_ms.year + 1, month=1) if _ms.month == 12 else _ms.replace(month=_ms.month + 1)

    # ── Filtro base por papel ──────────────────────────────────────────────
    e_admin = papel == 'Administrador'
    e_gestor = e_admin or papel in ("Gestor Financeiro",)

    # ── 1. Processos Aduaneiros ─────────────────────────────────────────────
    if e_admin:
        dus_qs = DeclaracaoUnica.objects.all()
    else:
        dus_qs = DeclaracaoUnica.objects.filter(usuario_id=uid)
    dus_ativas = dus_qs.order_by("-created_at")[:8]
    stats_dus_total = dus_qs.count()
    stats_dus_ativos = dus_qs.filter(status__in=["Rascunho", "Submetida", "Em Análise"]).count()
    stats_dus_mes = dus_qs.filter(
        created_at__gte=_ms, created_at__lt=_me
    ).aggregate(total=Sum('total_geral'))['total'] or 0

    # ── 2. Clientes ────────────────────────────────────────────────────────
    if e_gestor:
        clientes_qs = Cliente.objects.all()
    else:
        clientes_qs = Cliente.objects.filter(usuario_id=uid)
    stats_clientes = clientes_qs.filter(ativo=True).count()

    # ── 3. Facturação do mês ───────────────────────────────────────────────
    if e_gestor:
        fact_mes_qs = FacturaCliente.objects.all()
    else:
        fact_mes_qs = FacturaCliente.objects.filter(cliente__usuario_id=uid)
    fact_mes = fact_mes_qs.filter(
        data_emissao__gte=_ms, data_emissao__lt=_me
    ).aggregate(total=Sum('valor_total'))['total'] or 0
    stats_fact_valor = fact_mes
    stats_fact_qtd = fact_mes_qs.filter(
        data_emissao__gte=_ms, data_emissao__lt=_me
    ).count()

    # ── 4. Colaboradores ────────────────────────────────────────────────────
    if e_gestor:
        cols_qs = Colaborador.objects.all()
    else:
        banca = Banca.objects.filter(usuario_id=uid, ativa=True).first()
        cols_qs = Colaborador.objects.filter(banca=banca) if banca else Colaborador.objects.none()
    stats_colab_total = cols_qs.count()
    stats_colab_ativos = cols_qs.filter(estado='Ativo').count()

    # ── 6. Utilizadores (apenas administradores) ─────────────────────────────
    if e_admin:
        from users.models import Usuario
        stats_utilizadores_total = Usuario.objects.exclude(papel='Administrador').count()
        stats_utilizadores_ativos = Usuario.objects.exclude(papel='Administrador').filter(status='Ativo').count()
    else:
        stats_utilizadores_total = 0
        stats_utilizadores_ativos = 0

    # ── 7. Notificações ─────────────────────────────────────────────────────
    stats_notificacoes = Notificacao.objects.filter(
        usuario_id=uid, lida=False
    ).count()

    # ── Pendentes de Aprovação (NC + ND + Requisições de Fundos) ──────────
    if e_gestor:
        nc_pend = NotaCredito.objects.filter(estado='Pendente').count()
        nd_pend = NotaDebito.objects.filter(estado='Pendente').count()
    else:
        nc_pend = NotaCredito.objects.filter(estado='Pendente', cliente__usuario_id=uid).count()
        nd_pend = NotaDebito.objects.filter(estado='Pendente', cliente__usuario_id=uid).count()
    stats_nc_pendentes = nc_pend
    stats_nd_pendentes = nd_pend

    # ── Requisições de Fundos Pendentes ─────────────────────────────────
    from financeiro.models import RequisicaoFundo
    if e_gestor:
        stats_requisicoes_pendentes = RequisicaoFundo.objects.filter(estado='Pendente').count()
    else:
        stats_requisicoes_pendentes = RequisicaoFundo.objects.filter(
            estado='Pendente', cliente__usuario_id=uid
        ).count()

    # ── Top devedores (clientes com saldo negativo — devem dinheiro) ──────
    top_devedores = clientes_qs.filter(ativo=True, saldo_conta_corrente__lt=0
    ).order_by('saldo_conta_corrente')[:5]

    # ── Actividade recente (últimos históricos financeiros) ─────────────────
    from financeiro.models import HistoricoFinanceiro
    if e_gestor:
        recente = HistoricoFinanceiro.objects.order_by('-data')[:10]
    else:
        recente = HistoricoFinanceiro.objects.filter(utilizador_id=uid).order_by('-data')[:10]

    user_permissoes = get_usuario_permissoes(request)

    return render(request, "dashboard.html", {
        "usuario": usuario,
        "nome": usuario["nome"],
        "papel": papel,
        "active_menu": "Dashboard",
        "user_permissoes": user_permissoes,
        "tempo_restante_sessao": tempo_restante_sessao(request),
        "dus_ativas": dus_ativas,
        "stats_dus_total": stats_dus_total,
        "stats_dus_ativos": stats_dus_ativos,
        "stats_dus_mes": stats_dus_mes,
        "stats_clientes": stats_clientes,
        "stats_fact_valor": stats_fact_valor,
        "stats_fact_qtd": stats_fact_qtd,
        "stats_requisicoes_pendentes": stats_requisicoes_pendentes,
        "stats_colab_total": stats_colab_total,
        "stats_colab_ativos": stats_colab_ativos,
        "stats_utilizadores_total": stats_utilizadores_total,
        "stats_utilizadores_ativos": stats_utilizadores_ativos,
        "stats_notificacoes": stats_notificacoes,
        "stats_nc_pendentes": stats_nc_pendentes,
        "stats_nd_pendentes": stats_nd_pendentes,
        "top_devedores": top_devedores,
        "recente": recente,
    })


def dashboard_colaborador_view(request):
    """Dashboard para colaboradores."""
    if not request.session.get("usuario_id"):
        return redirect("login")
    if sessao_expirada(request):
        limpar_sessao(request)
        return redirect("login")
    if request.session.get("tipo_usuario") != "colaborador":
        return redirect("login")

    from users.permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)

    # ── Colaborador Institucional sem função (não tem rh_Colaborador) ──
    colaborador_id = request.session.get("colaborador_id")
    if not colaborador_id:
        from governanca.models import Notificacao
        uid = request.session.get("usuario_id")
        papel_sessao = request.session.get("usuario", {}).get("papel", "Colaborador Institucional")
        contexto = {
            "usuario": request.session.get("usuario", {}),
            "nome": request.session.get("usuario", {}).get("nome", ""),
            "papel": papel_sessao,
            "active_menu": "Dashboard",
            "tempo_restante_sessao": tempo_restante_sessao(request),
            "user_permissoes": permissoes,
            "stats_notificacoes": Notificacao.objects.filter(
                usuario_id=uid, lida=False
            ).count() if uid else 0,
        }
        return render(request, "colaboradores/dashboard_institucional.html", contexto)

    # ── Ver Dashboard global (colaborador banca com permissão) ─────────────
    if 'ver_dashboard' in permissoes:
        from aduaneiro.models import DeclaracaoUnica
        from clientes.models import Cliente
        from financeiro.models import FacturaCliente
        from governanca.models import Notificacao
        from django.utils import timezone as tz
        from django.db.models import Sum, Q

        _ms = tz.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _me = _ms.replace(year=_ms.year + 1, month=1) if _ms.month == 12 else _ms.replace(month=_ms.month + 1)

        dono_id = request.session.get('usuario_id')
        col_obj = Colaborador.objects.select_related('banca').filter(
            pk=colaborador_id, estado='Ativo'
        ).first()
        if col_obj and col_obj.banca:
            dono_id = col_obj.banca.usuario_id

        dus_qs = DeclaracaoUnica.objects.filter(usuario_id=dono_id)
        clientes_qs = Cliente.objects.filter(usuario_id=dono_id)
        fact_mes_qs = FacturaCliente.objects.filter(cliente__usuario_id=dono_id)

        dus_ativas = dus_qs.order_by("-created_at")[:8]
        dus_total = dus_qs.count()
        dus_status = dus_qs.filter(status__in=["Rascunho", "Submetida", "Em Análise"]).count()
        dus_mes = dus_qs.filter(
            created_at__gte=_ms, created_at__lt=_me
        ).aggregate(total=Sum('total_geral'))['total'] or 0

        fact_mes = fact_mes_qs.filter(
            data_emissao__gte=_ms, data_emissao__lt=_me
        ).aggregate(total=Sum('valor_total'))['total'] or 0
        fact_qtd = fact_mes_qs.filter(
            data_emissao__gte=_ms, data_emissao__lt=_me
        ).count()

        from financeiro.models import RequisicaoFundo
        req_pend_qs = RequisicaoFundo.objects.filter(
            estado='Pendente', cliente__usuario_id=dono_id
        )
        try:
            col_dash = Colaborador.objects.select_related('cargo_banca', 'banca').get(id=colaborador_id)
        except Colaborador.DoesNotExist:
            return redirect("login")

        top_devedores = clientes_qs.filter(ativo=True, saldo_conta_corrente__lt=0).order_by('saldo_conta_corrente')[:5]

        from financeiro.models import HistoricoFinanceiro
        try:
            recente = HistoricoFinanceiro.objects.order_by('-data')[:10]
        except Exception:
            recente = []

        contexto = {
            "usuario": request.session.get("usuario", {}),
            "nome": col_dash.nome,
            "papel": col_dash.cargo_banca.nome if col_dash.cargo_banca else "Colaborador",
            "active_menu": "Dashboard",
            "user_permissoes": permissoes,
            "tempo_restante_sessao": tempo_restante_sessao(request),
            "dus_ativas": dus_ativas,
            "stats_dus_total": dus_total,
            "stats_dus_ativos": dus_status,
            "stats_dus_mes": dus_mes,
            "stats_clientes": clientes_qs.filter(ativo=True).count(),
            "stats_fact_valor": fact_mes,
            "stats_fact_qtd": fact_qtd,
            "stats_requisicoes_pendentes": req_pend_qs.count(),
            "stats_colab_total": col_dash.banca.colaboradores.count() if col_dash.banca else 0,
            "stats_colab_ativos": col_dash.banca.colaboradores.filter(estado='Ativo').count() if col_dash.banca else 0,
            "stats_notificacoes": Notificacao.objects.filter(usuario_id=dono_id, lida=False).count(),
            "top_devedores": top_devedores,
            "recente": recente,
        }
        return render(request, "dashboard.html", contexto)

    # ── Dashboard simples de colaborador da banca ─────────────────────────
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect("login")
    papel = colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador"
    e_gestor = colaborador.e_gestor_filial
    try:
        filial_gestor = colaborador.gestor_filial.filial if e_gestor else None
    except Exception:
        filial_gestor = None

    contexto = {
        "usuario": request.session.get("usuario", {}),
        "nome": colaborador.nome,
        "papel": papel,
        "active_menu": "Dashboard",
        "tempo_restante_sessao": tempo_restante_sessao(request),
        "colaborador": colaborador,
        "colaborador_logado": colaborador,
        "e_responsavel": e_gestor,
        "e_gestor_filial": e_gestor,
        "filial_gestor": filial_gestor,
        "user_permissoes": permissoes,
    }

    template = (
        "colaboradores/responsavel_dashboard.html"
        if colaborador.e_gestor_filial
        else "colaboradores/dashboard.html"
    )
    return render(request, template, contexto)


# ─── Utilitário de teste de email ─────────────────────────────────────────────

@requer_sessao_ativa
def testar_email_view(_request):
    """Testa a ligação SMTP e envia email de diagnóstico."""
    import smtplib
    import ssl as ssl_lib
    from django.core.mail import EmailMultiAlternatives

    linhas = []

    # 1. Verificar configuração
    linhas.append(f"EMAIL_HOST      : {settings.EMAIL_HOST}")
    linhas.append(f"EMAIL_PORT      : {settings.EMAIL_PORT}")
    linhas.append(f"EMAIL_USE_TLS   : {settings.EMAIL_USE_TLS}")
    linhas.append(f"EMAIL_HOST_USER : {settings.EMAIL_HOST_USER}")
    pwd = settings.EMAIL_HOST_PASSWORD or ""
    linhas.append(f"PASSWORD length : {len(pwd)} chars")
    linhas.append("")

    # 2. Testar ligação SMTP directa
    try:
        ctx = ssl_lib.create_default_context()
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT, timeout=20) as srv:
            srv.ehlo()
            srv.starttls(context=ctx)
            srv.ehlo()
            linhas.append("✅ STARTTLS: OK")
            srv.login(settings.EMAIL_HOST_USER, pwd)
            linhas.append("✅ LOGIN: OK")
    except smtplib.SMTPAuthenticationError as e:
        linhas.append(f"❌ LOGIN FALHOU: {e}")
        linhas.append("")
        linhas.append("SOLUÇÃO:")
        linhas.append("1. Aceda a https://myaccount.google.com/security")
        linhas.append("2. Active a Verificação em 2 Passos")
        linhas.append("3. Pesquise 'App passwords' e crie uma nova")
        linhas.append("4. Copie os 16 caracteres SEM espaços para settings.py")
        return HttpResponse("<pre>" + "\n".join(linhas) + "</pre>", status=500)
    except Exception as exc:  # noqa: BLE001
        linhas.append(f"❌ ERRO DE LIGAÇÃO: {exc}")
        return HttpResponse("<pre>" + "\n".join(linhas) + "</pre>", status=500)

    # 3. Enviar email de teste via Django
    try:
        msg = EmailMultiAlternatives(
            subject="[SICDOA] Teste de Email",
            body="Email de teste do sistema SICDOA. Se recebeu este email, a configuração está correcta.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.EMAIL_HOST_USER],
        )
        msg.send(fail_silently=False)
        linhas.append("✅ EMAIL ENVIADO com sucesso!")
        linhas.append(f"   Verifique a caixa de entrada de {settings.EMAIL_HOST_USER}")
    except Exception as exc:  # noqa: BLE001
        linhas.append(f"❌ ERRO AO ENVIAR: {exc}")

    return HttpResponse("<pre>" + "\n".join(linhas) + "</pre>")


# ─── Portal do Colaborador ────────────────────────────────────────────────────

def perfil_view(request):
    """Perfil do colaborador — editar dados pessoais e palavra-passe."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None  # flag: usamos modelos institucionais?
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    from .permissoes import usuario_tem_permissao, get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    pode_editar = 'alterar_perfil' in permissoes

    if request.method == "POST":
        acao = request.POST.get("acao", "")

        if acao == "editar_perfil" and not pode_editar:
            messages.error(request, 'Não tem permissão para alterar o perfil.')
            return redirect("colaborador_perfil")

        if acao == "editar_perfil":
            obj = institucional if institucional else colaborador
            obj.nome = request.POST.get("nome", "").strip() or obj.nome
            obj.telefone = request.POST.get("telefone", "").strip()
            obj.email = request.POST.get("email", "").strip()
            obj.save(update_fields=["nome", "telefone", "email"])
            messages.success(request, "Perfil actualizado com sucesso.")
            return redirect("colaborador_perfil")

        if acao == "alterar_password":
            usuario_id = request.session.get("usuario_id")
            senha_actual = request.POST.get("senha_actual", "")
            nova_senha = request.POST.get("nova_senha", "")
            confirmar = request.POST.get("confirmar_senha", "")

            if request.session.get("tipo_usuario") == "colaborador":
                from rh.models import Colaborador as _Col
                try:
                    user_obj = _Col.objects.get(pk=usuario_id)
                except _Col.DoesNotExist:
                    messages.error(request, "Utilizador não encontrado.")
                    return redirect("colaborador_perfil")
                hash_actual = user_obj.password or ""
            else:
                from .models import Usuario
                try:
                    user_obj = Usuario.objects.get(pk=usuario_id)
                except Usuario.DoesNotExist:
                    messages.error(request, "Utilizador não encontrado.")
                    return redirect("colaborador_perfil")
                hash_actual = user_obj.password or ""

            if not _verificar_password(senha_actual, hash_actual):
                messages.error(request, "A palavra-passe actual está incorrecta.")
            elif len(nova_senha) < 8:
                messages.error(request, "A nova palavra-passe deve ter pelo menos 8 caracteres.")
            elif not any(c.isupper() for c in nova_senha):
                messages.error(request, "A nova palavra-passe deve conter pelo menos uma letra maiúscula.")
            elif not any(c.isdigit() for c in nova_senha):
                messages.error(request, "A nova palavra-passe deve conter pelo menos um dígito.")
            elif nova_senha != confirmar:
                messages.error(request, "As palavras-passe não coincidem.")
            else:
                user_obj.password = _hash_password(nova_senha)
                user_obj.save(update_fields=["password"])
                messages.success(request, "Palavra-passe alterada com sucesso.")
                return redirect("colaborador_perfil")

    if institucional:
        papel = institucional.area_actuacao or "Colaborador"
        return render(request, "colaboradores/perfil_institucional.html", {
            "nome": institucional.nome,
            "papel": papel,
            "active_menu": "Meus Dados",
            "active_sub": "perfil",
            "colaborador": institucional,
            "colaborador_logado": institucional,
            "e_responsavel": False,
            "user_permissoes": permissoes,
            "pode_editar_perfil": pode_editar,
        })

    # Banca colaborador
    papel = colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador"
    documentos = DocumentoColaborador.objects.filter(
        colaborador=colaborador
    ).order_by("-criado_em")
    return render(request, "colaboradores/perfil.html", {
        "nome": colaborador.nome,
        "papel": papel,
        "active_menu": "Meus Dados",
        "active_sub": "perfil",
        "colaborador": colaborador,
        "colaborador_logado": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "pode_editar_perfil": pode_editar,
        "documentos": documentos,
    })


def documentos_view(request):
    """Documentos do colaborador."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if not colaborador:
        institucional = _get_institucional(request)
        if institucional:
            messages.info(request, "Documentos não disponíveis para contas institucionais.")
            return redirect("dashboard_colaborador")
        return erro or redirect("login")

    documentos = DocumentoColaborador.objects.filter(
        colaborador=colaborador
    ).order_by("-criado_em")

    paginator = Paginator(documentos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    papel = colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador"
    return render(request, "colaboradores/documentos.html", {
        "nome": colaborador.nome,
        "papel": papel,
        "active_menu": "Meus Dados",
        "active_sub": "documentos",
        "colaborador": colaborador,
        "colaborador_logado": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "documentos": page_obj,
        "page_obj": page_obj,
    })


def presenca_view(request):
    """Marcar presença — regista entrada ou saída do dia."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    hoje = timezone.localdate()
    e_inst = institucional is not None
    obj = institucional if e_inst else colaborador

    # Resolve registo de hoje
    if e_inst:
        registo_hoje = PresencaInstitucional.objects.filter(colaborador=obj, data=hoje).first()
    else:
        registo_hoje = RegistoPresenca.objects.filter(colaborador=obj, data=hoje).first()

    if request.method == "POST":
        acao = request.POST.get("acao")
        agora = timezone.localtime(timezone.now()).time()
        if e_inst:
            registo_hoje = PresencaInstitucional.objects.filter(colaborador=obj, data=hoje).first()
        else:
            registo_hoje = RegistoPresenca.objects.filter(colaborador=obj, data=hoje).first()

        if acao == "entrada":
            if registo_hoje:
                messages.error(request, "Já registou a entrada hoje.")
            else:
                if e_inst:
                    PresencaInstitucional.objects.create(
                        colaborador=obj, data=hoje, tipo="Entrada",
                        hora_entrada=agora, estado="Pendente",
                    )
                else:
                    RegistoPresenca.objects.create(
                        colaborador=obj, data=hoje, tipo="Entrada",
                        hora_entrada=agora, estado="Pendente",
                    )
                messages.success(request, f"Entrada registada às {agora.strftime('%H:%M')}.")
                return redirect("colaborador_presenca")

        elif acao == "saida":
            if not registo_hoje:
                messages.error(request, "Precisa de registar a entrada primeiro.")
            elif registo_hoje.hora_saida:
                messages.error(request, "Já registou a saída hoje.")
            else:
                registo_hoje.hora_saida = agora
                registo_hoje.save(update_fields=["hora_saida"])
                messages.success(request, f"Saída registada às {agora.strftime('%H:%M')}.")
                return redirect("colaborador_presenca")

    if e_inst:
        historico_qs = PresencaInstitucional.objects.filter(colaborador=obj).order_by("-data")
    else:
        historico_qs = RegistoPresenca.objects.filter(colaborador=obj).order_by("-data")

    paginator = Paginator(historico_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats do mes actual
    from datetime import date as date_cls
    registos_mes_qs = RegistoPresenca.objects.filter(colaborador=obj, data__year=hoje.year, data__month=hoje.month) if not e_inst else PresencaInstitucional.objects.filter(colaborador=obj, data__year=hoje.year, data__month=hoje.month)
    total_mes = registos_mes_qs.count()
    aprovados_mes = registos_mes_qs.filter(estado='Aprovado').count()
    pendentes_mes = registos_mes_qs.filter(estado='Pendente').count()

    papel = obj.area_actuacao or (colaborador.cargo_banca.nome if not e_inst and colaborador.cargo_banca else "Colaborador") if e_inst else (colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador")
    if e_inst:
        papel = obj.area_actuacao or "Colaborador"
    else:
        papel = colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador"

    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    return render(request, "colaboradores/presenca.html", {
        "nome": obj.nome,
        "papel": papel,
        "active_menu": "RH",
        "active_sub": "presenca",
        "colaborador": obj,
        "colaborador_logado": obj,
        "e_responsavel": False if e_inst else colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "hoje": hoje,
        "registo_hoje": registo_hoje,
        "historico": page_obj,
        "page_obj": page_obj,
        "total_mes": total_mes,
        "aprovados_mes": aprovados_mes,
        "pendentes_mes": pendentes_mes,
    })


def processo_salarial_view(request):
    """Página central do Processo Salarial com links para Ver Salário e Histórico."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    e_inst = institucional is not None
    obj = institucional if e_inst else colaborador
    papel = obj.area_actuacao or "Colaborador" if e_inst else (colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador")
    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    return render(request, "colaboradores/processo_salarial.html", {
        "nome": obj.nome,
        "papel": papel,
        "active_menu": "RH",
        "active_sub": "salario",
        "colaborador": obj,
        "colaborador_logado": obj,
        "e_responsavel": False if e_inst else colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
    })


def salario_view(request):
    """Processo salarial — 8 recibos por página, mais recente primeiro."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    e_inst = institucional is not None
    obj = institucional if e_inst else colaborador
    ModelRecibo = ReciboSalarialInstitucional if e_inst else ReciboSalarial

    todos = ModelRecibo.objects.filter(
        colaborador=obj
    ).select_related("processamento").order_by(
        "-processamento__ano", "-processamento__mes"
    )

    paginator = Paginator(todos, 8)
    try:
        pagina_num = int(request.GET.get("pagina", 1))
    except (ValueError, TypeError):
        pagina_num = 1
    pagina = paginator.get_page(pagina_num)

    papel = obj.area_actuacao or "Colaborador" if e_inst else (colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador")
    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    return render(request, "colaboradores/salario.html", {
        "nome": obj.nome,
        "papel": papel,
        "active_menu": "RH",
        "active_sub": "salario",
        "colaborador": obj,
        "colaborador_logado": obj,
        "e_responsavel": False if e_inst else colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "recibos": pagina,
        "paginator": paginator,
        "pagina_actual": pagina_num,
        "recibo_mais_recente": todos.first(),
        "total_recibos": todos.count(),
        "salario_base": obj.salario_base or 0,
    })


def historico_salarial_view(request):
    """Histórico salarial completo — 8 por página."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    e_inst = institucional is not None
    obj = institucional if e_inst else colaborador
    ModelRecibo = ReciboSalarialInstitucional if e_inst else ReciboSalarial

    todos = ModelRecibo.objects.filter(
        colaborador=obj
    ).select_related("processamento").order_by(
        "-processamento__ano", "-processamento__mes"
    )

    paginator = Paginator(todos, 8)
    try:
        pagina_num = int(request.GET.get("pagina", 1))
    except (ValueError, TypeError):
        pagina_num = 1
    pagina = paginator.get_page(pagina_num)

    papel = obj.area_actuacao or "Colaborador" if e_inst else (colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador")
    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    return render(request, "colaboradores/historico_salarial.html", {
        "nome": obj.nome,
        "papel": papel,
        "active_menu": "RH",
        "active_sub": "historico-salarial",
        "colaborador": obj,
        "colaborador_logado": obj,
        "e_responsavel": False if e_inst else colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "recibos": pagina,
        "paginator": paginator,
        "pagina_actual": pagina_num,
        "total_recibos": todos.count(),
        "salario_base": obj.salario_base or 0,
    })


def ferias_view(request):
    """Pedido de férias — submete e lista pedidos anteriores."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    institucional = None
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return erro or redirect("login")

    e_inst = institucional is not None
    obj = institucional if e_inst else colaborador

    if request.method == "POST":
        inicio_str = request.POST.get("data_inicio", "").strip()
        fim_str = request.POST.get("data_fim", "").strip()
        motivo = request.POST.get("motivo", "").strip()

        if not inicio_str or not fim_str:
            messages.error(request, "Preencha as datas de início e fim.")
        else:
            try:
                data_inicio = date.fromisoformat(inicio_str)
                data_fim = date.fromisoformat(fim_str)
                hoje = timezone.localdate()

                if data_fim < data_inicio:
                    messages.error(request, "A data de fim não pode ser anterior à data de início.")
                elif data_inicio < hoje:
                    messages.error(request, "A data de início não pode ser no passado.")
                elif (FeriasInstitucional if e_inst else PedidoFerias).objects.filter(
                    colaborador=obj,
                    estado__in=["Pendente", "Aprovado"],
                    data_inicio__lte=data_fim,
                    data_fim__gte=data_inicio,
                ).exists():
                    messages.error(request, "Já existe um pedido de férias nesse período.")
                else:
                    (FeriasInstitucional if e_inst else PedidoFerias).objects.create(
                        colaborador=obj,
                        data_inicio=data_inicio,
                        data_fim=data_fim,
                        motivo=motivo,
                        estado="Pendente",
                    )
                    if not e_inst:
                        try:
                            from rh.views import _actualizar_saldo_pos_criacao
                            pedido_novo = PedidoFerias.objects.filter(colaborador=obj).order_by('-criado_em').first()
                            if pedido_novo:
                                _actualizar_saldo_pos_criacao(pedido_novo)
                        except Exception:
                            pass
                    messages.success(
                        request,
                        "Pedido de férias submetido com sucesso. Aguarde aprovação.",
                    )
                    return redirect("colaborador_ferias")
            except ValueError:
                messages.error(request, "Datas inválidas.")

    ModelFerias = FeriasInstitucional if e_inst else PedidoFerias
    pedidos = ModelFerias.objects.filter(colaborador=obj).order_by("-criado_em")

    paginator = Paginator(pedidos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    papel = obj.area_actuacao or "Colaborador" if e_inst else (colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador")
    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)

    saldo_ferias = None
    saldo_anterior = None
    if not e_inst and colaborador:
        try:
            from rh.views import obter_ou_criar_saldo
            from datetime import date as date_cls
            saldo_ferias = obter_ou_criar_saldo(colaborador, date.today().year)
            saldo_anterior = obter_ou_criar_saldo(colaborador, date.today().year - 1)
        except Exception:
            pass

    # Build visual calendar data for current month
    hoje_date = timezone.localdate()
    import calendar as cal_mod
    cal_days = cal_mod.monthcalendar(hoje_date.year, hoje_date.month)
    approved_days = set()
    pending_days = set()
    if saldo_ferias:
        pedidos_para_calendario = ModelFerias.objects.filter(
            colaborador=obj,
            estado__in=["Aprovado", "Pendente"],
            data_inicio__year=hoje_date.year,
        )
        for p in pedidos_para_calendario:
            d = max(p.data_inicio, hoje_date.replace(day=1))
            fim = min(p.data_fim, hoje_date.replace(day=cal_mod.monthrange(hoje_date.year, hoje_date.month)[1]))
            while d <= fim:
                if d.month == hoje_date.month:
                    if p.estado == "Aprovado":
                        approved_days.add(d.day)
                    else:
                        pending_days.add(d.day)
                d += __import__('datetime').timedelta(days=1)

    return render(request, "colaboradores/ferias.html", {
        "nome": obj.nome,
        "papel": papel,
        "active_menu": "RH",
        "active_sub": "ferias",
        "colaborador": obj,
        "colaborador_logado": obj,
        "e_responsavel": False if e_inst else colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
        "pedidos": page_obj,
        "page_obj": page_obj,
        "saldo": saldo_ferias,
        "saldo_anterior": saldo_anterior,
        "hoje": hoje_date,
        "cal_year": hoje_date.year,
        "cal_month": hoje_date.month,
        "cal_month_name": ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"][hoje_date.month],
        "cal_days": cal_days,
        "approved_days": approved_days,
        "pending_days": pending_days,
    })


def buscar_view(request):
    """Resultados de busca para colaboradores."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro
    if not colaborador:
        institucional = _get_institucional(request)
        if not institucional:
            return redirect("login")
        return redirect("dashboard_colaborador")

    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("dashboard_colaborador")

    from .permissoes import get_usuario_permissoes
    permissoes = get_usuario_permissoes(request)
    papel = colaborador.cargo_banca.nome if colaborador.cargo_banca else "Colaborador"
    return render(request, "colaboradores/buscar.html", {
        "nome": colaborador.nome,
        "papel": papel,
        "active_menu": "Dashboard",
        "query": query,
        "colaborador": colaborador,
        "colaborador_logado": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "user_permissoes": permissoes,
    })


# ─── Perfil do utilizador (despachante / admin / operador) ───────────────────

def _verificar_sessao_usuario(request):
    """Verifica sessão activa de utilizador (não colaborador)."""
    if not request.session.get("usuario_id"):
        return None, redirect("login")
    if sessao_expirada(request):
        limpar_sessao(request)
        return None, redirect("login")
    uid = request.session.get("usuario_id")
    try:
        return Usuario.objects.get(id=uid), None
    except Usuario.DoesNotExist:
        return None, redirect("login")


def meu_perfil_view(request):
    """Página de perfil do utilizador."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro

    cargo_info = None

    from aduaneiro.models import DeclaracaoUnica
    total_dus   = DeclaracaoUnica.objects.filter(usuario_id=usuario.id).count()
    _ms = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _me = _ms.replace(year=_ms.year + 1, month=1) if _ms.month == 12 else _ms.replace(month=_ms.month + 1)
    dus_mes = DeclaracaoUnica.objects.filter(
        usuario_id=usuario.id,
        created_at__gte=_ms, created_at__lt=_me
    ).count()

    from .permissoes import usuario_tem_permissao
    pode_editar_perfil = usuario_tem_permissao(request, 'alterar_perfil')

    return render(request, "meu_perfil.html", {
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email,
            "papel": usuario.papel,
            "username": usuario.username,
            "nif": usuario.nif or "",
            "telefone": usuario.telefone or "",
            "cedula": usuario.cedula or "",
            "foto": usuario.foto or "",
            "status": usuario.status,
            "ultimo_acesso": usuario.ultimo_acesso,
            "assinatura": usuario.assinatura or "",
            "assinatura_data": usuario.assinatura_data,
        },
        "cargo_info": cargo_info,
        "tem_senha": bool(usuario.password),
        "nome": usuario.nome,
        "papel": usuario.papel,
        "active_menu": "Perfil",
        "total_dus": total_dus,
        "dus_mes": dus_mes,
        "pode_editar_perfil": pode_editar_perfil,
        "tem_assinatura": bool(usuario.assinatura),
        "messages": messages.get_messages(request),
    })


def meu_perfil_guardar(request):
    """Guarda alterações ao perfil via POST — nome, username e telefone."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
        return redirect("meu_perfil")

    from .permissoes import usuario_tem_permissao
    if not usuario_tem_permissao(request, 'alterar_perfil'):
        messages.error(request, 'Não tem permissão para alterar o perfil.')
        return redirect("meu_perfil")

    nome     = request.POST.get("nome", "").strip()
    username = request.POST.get("username", "").strip()
    telefone = request.POST.get("telefone", "").strip()

    # ── Validação ─────────────────────────────────────────────────────────
    if not nome:
        messages.error(request, "O nome não pode estar vazio.")
        return redirect("meu_perfil")
    if len(nome) < 2:
        messages.error(request, "O nome deve ter pelo menos 2 caracteres.")
        return redirect("meu_perfil")
    if len(nome) > 100:
        messages.error(request, "O nome não pode ter mais de 100 caracteres.")
        return redirect("meu_perfil")

    if not username:
        messages.error(request, "O username não pode estar vazio.")
        return redirect("meu_perfil")
    if len(username) < 3:
        messages.error(request, "O username deve ter pelo menos 3 caracteres.")
        return redirect("meu_perfil")
    if len(username) > 50:
        messages.error(request, "O username não pode ter mais de 50 caracteres.")
        return redirect("meu_perfil")
    import re as _re
    if not _re.match(r'^[\w]+$', username):
        messages.error(request, "O username só pode conter letras, números e underscore.")
        return redirect("meu_perfil")
    # Verificar unicidade (excluindo o próprio utilizador)
    if Usuario.objects.filter(username=username).exclude(id=usuario.id).exists():
        messages.error(request, f'O username "{username}" já está em uso.')
        return redirect("meu_perfil")

    if telefone and len(telefone) > 20:
        messages.error(request, "Número de telefone inválido.")
        return redirect("meu_perfil")

    from django.db import connection as _conn
    with _conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET nome=%s, username=%s, telefone=%s, updated_at=%s WHERE id=%s",
            [nome, username, telefone, timezone.now(), usuario.id],
        )

    # Actualizar sessão
    sess = request.session.get("usuario", {})
    sess["nome"] = nome
    request.session["usuario"] = sess
    request.session.modified = True

    messages.success(request, "Perfil actualizado com sucesso.")
    return redirect("meu_perfil")


def meu_perfil_senha(request):
    """Altera a senha do utilizador."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
        return redirect("meu_perfil")

    from .permissoes import usuario_tem_permissao
    if not usuario_tem_permissao(request, 'alterar_perfil'):
        messages.error(request, 'Não tem permissão para alterar a senha.')
        return redirect("meu_perfil")

    senha_atual  = request.POST.get("senha_atual", "").strip()
    nova_senha   = request.POST.get("nova_senha", "").strip()
    confirmar    = request.POST.get("confirmar_senha", "").strip()

    # ── Validação server-side ─────────────────────────────────────────────
    
    # Se usuário não tem senha (criado via portal), não precisa de senha atual
    tem_senha = usuario.password is not None and usuario.password != ''
    
    if tem_senha:
        # Usuário tem senha: validar senha atual
        if not senha_atual:
            messages.error(request, "Preencha a senha actual.")
            return redirect("meu_perfil")
        
        if not _verificar_password(senha_atual, usuario.password):
            messages.error(request, "A senha actual está incorrecta.")
            return redirect("meu_perfil")
    else:
        # Usuário não tem senha: está definindo pela primeira vez
        if not nova_senha or not confirmar:
            messages.error(request, "Preencha a nova senha e a confirmação.")
            return redirect("meu_perfil")
    
    # Validar nova senha
    if not nova_senha or not confirmar:
        messages.error(request, "Preencha todos os campos de senha.")
        return redirect("meu_perfil")
    
    if len(nova_senha) < 8:
        messages.error(request, "A nova senha deve ter pelo menos 8 caracteres.")
        return redirect("meu_perfil")

    if not any(c.isupper() for c in nova_senha):
        messages.error(request, "A nova senha deve conter pelo menos uma letra maiúscula.")
        return redirect("meu_perfil")

    if not any(c.isdigit() for c in nova_senha):
        messages.error(request, "A nova senha deve conter pelo menos um dígito.")
        return redirect("meu_perfil")

    if len(nova_senha) > 128:
        messages.error(request, "A senha é demasiado longa.")
        return redirect("meu_perfil")
    
    if nova_senha != confirmar:
        messages.error(request, "As senhas não coincidem.")
        return redirect("meu_perfil")
    
    if tem_senha and nova_senha == senha_atual:
        messages.error(request, "A nova senha não pode ser igual à senha actual.")
        return redirect("meu_perfil")
    
    # Criar hash e salvar
    novo_hash = _hash_password(nova_senha)
    from django.db import connection as _conn
    with _conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET password=%s, updated_at=%s WHERE id=%s",
            [novo_hash, timezone.now(), usuario.id],
        )
    
    if tem_senha:
        messages.success(request, "Senha alterada com sucesso.")
    else:
        messages.success(request, "Senha definida com sucesso! Agora pode usar o login tradicional.")

    return redirect("meu_perfil")


def meu_perfil_assinatura(request):
    """Guarda a assinatura digital do utilizador (canvas Base64 ou upload de imagem)."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
        return redirect("meu_perfil")

    from .permissoes import usuario_tem_permissao
    if not usuario_tem_permissao(request, 'alterar_perfil'):
        messages.error(request, 'Não tem permissão para alterar a assinatura.')
        return redirect("meu_perfil")

    if usuario.papel != 'Despachante Oficial':
        messages.error(request, 'Apenas Despachantes Oficiais podem criar assinatura digital.')
        return redirect("meu_perfil")

    assinatura = request.POST.get("assinatura", "").strip()
    ficheiro = request.FILES.get("assinatura_upload")

    if ficheiro:
        import base64 as _b64
        from django.core.files.uploadedfile import InMemoryUploadedFile
        tipo = ficheiro.content_type or 'image/png'
        dados = ficheiro.read()
        if len(dados) > 2 * 1024 * 1024:
            messages.error(request, 'A imagem não pode ter mais de 2MB.')
            return redirect("meu_perfil")
        if tipo not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
            messages.error(request, 'Formato inválido. Use PNG, JPG, GIF ou WebP.')
            return redirect("meu_perfil")
        b64 = _b64.b64encode(dados).decode('utf-8')
        assinatura = f'data:{tipo};base64,{b64}'
    elif assinatura and assinatura.startswith('data:image/'):
        pass
    else:
        messages.error(request, 'Assinatura inválida. Desenhe ou faça upload de uma imagem.')
        return redirect("meu_perfil")

    from django.db import connection as _conn
    with _conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET assinatura=%s, assinatura_data=%s, updated_at=%s WHERE id=%s",
            [assinatura, timezone.now(), timezone.now(), usuario.id],
        )

    messages.success(request, "Assinatura digital guardada com sucesso.")
    return redirect("meu_perfil")


def meu_perfil_foto(request):
    """Guarda a foto de perfil do utilizador (apenas Despachante Oficial)."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
        return redirect("meu_perfil")

    from .permissoes import usuario_tem_permissao
    if not usuario_tem_permissao(request, 'alterar_perfil'):
        messages.error(request, 'Não tem permissão para alterar a foto de perfil.')
        return redirect("meu_perfil")

    if usuario.papel != 'Despachante Oficial':
        messages.error(request, 'Apenas Despachantes Oficiais podem adicionar foto de perfil.')
        return redirect("meu_perfil")

    ficheiro = request.FILES.get("foto_upload")
    if not ficheiro:
        messages.error(request, 'Selecione uma imagem para a foto de perfil.')
        return redirect("meu_perfil")

    if ficheiro.size > 5 * 1024 * 1024:
        messages.error(request, 'A imagem não pode ter mais de 5MB.')
        return redirect("meu_perfil")

    tipo = ficheiro.content_type or ''
    if tipo not in ('image/png', 'image/jpeg', 'image/gif', 'image/webp'):
        messages.error(request, 'Formato inválido. Use PNG, JPG, GIF ou WebP.')
        return redirect("meu_perfil")

    # Apagar foto anterior se existir
    if usuario.foto:
        import os
        from django.conf import settings
        caminho_antigo = os.path.join(settings.MEDIA_ROOT, str(usuario.foto))
        if os.path.exists(caminho_antigo):
            os.remove(caminho_antigo)

    usuario.foto = ficheiro
    usuario.save(update_fields=['foto'])

    # Actualizar sessão
    sess = request.session.get("usuario", {})
    sess["foto"] = usuario.foto.url if usuario.foto else ""
    request.session["usuario"] = sess
    request.session.modified = True

    messages.success(request, "Foto de perfil actualizada com sucesso.")
    return redirect("meu_perfil")


def meu_perfil_foto_remover(request):
    """Remove a foto de perfil do utilizador (apenas Despachante Oficial)."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
        return redirect("meu_perfil")

    if usuario.papel != 'Despachante Oficial':
        messages.error(request, 'Apenas Despachantes Oficiais podem remover a foto de perfil.')
        return redirect("meu_perfil")

    if usuario.foto:
        import os
        from django.conf import settings
        caminho = os.path.join(settings.MEDIA_ROOT, str(usuario.foto))
        if os.path.exists(caminho):
            os.remove(caminho)
        usuario.foto = ''
        usuario.save(update_fields=['foto'])

        sess = request.session.get("usuario", {})
        sess["foto"] = ""
        request.session["usuario"] = sess
        request.session.modified = True

    messages.success(request, "Foto de perfil removida com sucesso.")
    return redirect("meu_perfil")


# ─── Gestão de Funções (Papéis) ───────────────────────────────────────────────

def _requer_admin_ou_perm_funcoes(fn):
    """Decorator: só admin ou quem tem permissão 'gerir_utilizadores'."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        papel = request.session.get('usuario', {}).get('papel', '')
        if papel != 'Administrador':
            from .permissoes import usuario_tem_permissao
            if not usuario_tem_permissao(request, 'gerir_utilizadores'):
                messages.error(request, 'Acesso restrito a Administradores.')
                return redirect('dashboard')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


@_requer_admin_ou_perm_funcoes
def funcoes_lista_view(request):
    from .models import Funcao
    from django.db.models import Count
    q = request.GET.get('q', '').strip()
    funcoes = Funcao.objects.annotate(total_usuarios=Count('usuarios')).order_by('nome')
    if q:
        funcoes = funcoes.filter(nome__icontains=q)
    paginator = Paginator(funcoes, 12)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)
    papel = request.session.get('usuario', {}).get('papel', '')
    ctx = {
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'active_menu': 'RH_INST',
        'active_sub': 'funcoes',
        'funcoes': page_obj,
        'page_obj': page_obj,
        'q': q,
        'total': Funcao.objects.count(),
    }
    return render(request, 'users/funcoes_lista.html', ctx)


@_requer_admin_ou_perm_funcoes
def funcao_novo_view(request):
    from .models import Funcao, Permissao
    from .permissoes import PERMISSOES_BANCA, PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO, PERMISSOES_POR_MENU_INST
    papel = request.session.get('usuario', {}).get('papel', '')
    erros = {}
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        selected = request.POST.getlist('permissoes')
        if not nome:
            erros['nome'] = 'O nome é obrigatório.'
        elif Funcao.objects.filter(nome__iexact=nome).exists():
            erros['nome'] = 'Já existe uma função com este nome.'
        if not erros:
            funcao = Funcao.objects.create(nome=nome, descricao=descricao)
            if selected:
                funcao.permissoes.set(Permissao.objects.filter(codigo__in=selected))
            messages.success(request, f'Função "{nome}" criada com sucesso.')
            return redirect('funcoes_lista')
    ctx = {
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'active_menu': 'RH_INST',
        'active_sub': 'funcoes',
        'erros': erros,
        'is_edicao': False,
        'menus': PERMISSOES_POR_MENU_INST,
        'funcao_perm_codigos': set(),
        'funcao': None,
    }
    return render(request, 'users/funcao_form.html', ctx)


@_requer_admin_ou_perm_funcoes
def funcao_editar_view(request, pk):
    from .models import Funcao, Permissao
    from .permissoes import PERMISSOES_BANCA, PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO, PERMISSOES_POR_MENU_INST
    funcao = get_object_or_404(Funcao, pk=pk)
    papel = request.session.get('usuario', {}).get('papel', '')
    erros = {}
    funcao_perm_codigos = set(funcao.permissoes.values_list('codigo', flat=True))
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        descricao = request.POST.get('descricao', '').strip()
        selected = request.POST.getlist('permissoes')
        if not nome:
            erros['nome'] = 'O nome é obrigatório.'
        elif Funcao.objects.filter(nome__iexact=nome).exclude(pk=pk).exists():
            erros['nome'] = 'Já existe uma função com este nome.'
        if not erros:
            funcao.nome = nome
            funcao.descricao = descricao
            funcao.save()
            if selected:
                funcao.permissoes.set(Permissao.objects.filter(codigo__in=selected))
            else:
                funcao.permissoes.clear()
            messages.success(request, f'Função "{nome}" actualizada com sucesso.')
            return redirect('funcoes_lista')
    ctx = {
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'active_menu': 'RH_INST',
        'active_sub': 'funcoes',
        'funcao': funcao,
        'erros': erros,
        'is_edicao': True,
        'menus': PERMISSOES_POR_MENU_INST,
        'funcao_perm_codigos': funcao_perm_codigos,
    }
    return render(request, 'users/funcao_form.html', ctx)


@_requer_admin_ou_perm_funcoes
def funcao_permissoes_view(request, pk):
    from .models import Funcao, Permissao
    from .permissoes import PERMISSOES_BANCA, PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO
    funcao = get_object_or_404(Funcao, pk=pk)
    papel = request.session.get('usuario', {}).get('papel', '')
    permissoes = Permissao.objects.exclude(
        codigo__in=PERMISSOES_BANCA + PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO
    ).order_by('grupo', 'nome')
    funcao_perm_ids = list(funcao.permissoes.values_list('id', flat=True))
    ctx = {
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'active_menu': 'RH_INST',
        'active_sub': 'funcoes',
        'funcao': funcao,
        'permissoes': permissoes,
        'funcao_perm_ids': funcao_perm_ids,
    }
    return render(request, 'users/funcao_permissoes.html', ctx)


@_requer_admin_ou_perm_funcoes
def funcao_eliminar_view(request, pk):
    from .models import Funcao
    funcao = get_object_or_404(Funcao, pk=pk)
    if request.method == 'POST':
        nome = funcao.nome
        funcao.delete()
        messages.success(request, f'Função "{nome}" eliminada com sucesso.')
        return redirect('funcoes_lista')
    papel = request.session.get('usuario', {}).get('papel', '')
    ctx = {
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
        'active_menu': 'RH_INST',
        'active_sub': 'funcoes',
        'funcao': funcao,
        'total_usuarios': funcao.usuarios.count(),
    }
    return render(request, 'users/funcao_confirmar_eliminar.html', ctx)


@require_http_methods(['POST'])
@_requer_admin_ou_perm_funcoes
def api_funcao_permissoes(request):
    from .models import Funcao, Permissao
    from .permissoes import PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO
    data = json.loads(request.body)
    funcao_id = data.get('funcao_id')
    permissao_id = data.get('permissao_id')
    ativar = data.get('ativar', True)
    if not funcao_id or not permissao_id:
        return JsonResponse({'erro': 'Parâmetros incompletos.'}, status=400)
    funcao = get_object_or_404(Funcao, pk=funcao_id)
    permissao = get_object_or_404(Permissao, pk=permissao_id)
    if permissao.codigo in PERMISSOES_NAO_ATRIBUIVEIS_FUNCAO:
        return JsonResponse({
            'erro': f'A permissão "{permissao.nome}" não pode ser atribuída a Funções.'
        }, status=403)
    if ativar:
        funcao.permissoes.add(permissao)
    else:
        funcao.permissoes.remove(permissao)
    return JsonResponse({
        'status': 'ok',
        'message': f'{permissao.nome} {"ativada" if ativar else "desativada"} para a função {funcao.nome}.'
    })


@require_http_methods(['GET'])
@_requer_admin_ou_perm_funcoes
def api_funcao_listar_permissoes(request, pk):
    from .models import Funcao
    funcao = get_object_or_404(Funcao, pk=pk)
    permissoes_ids = list(funcao.permissoes.values_list('id', flat=True))
    return JsonResponse({'permissoes': permissoes_ids})


@requer_sessao_ativa
def logs_atividade_view(request):
    """Página de consulta de logs de atividade."""
    from .models import LogAtividade
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from django.db.models import Q
    from rh.models import Banca, Colaborador

    from users.permissoes import (
        _is_admin_ou_acesso_total,
        get_usuario_permissoes,
    )

    papel = request.session.get('usuario', {}).get('papel', '')
    usuario_id = request.session.get('usuario_id')
    permissoes = get_usuario_permissoes(request)

    # Despachante: vê logs da sua banca
    is_despachante = False
    banca = None
    if papel == 'Despachante Oficial' and usuario_id:
        banca = Banca.objects.filter(usuario_id=usuario_id, ativa=True).first()
        if banca:
            is_despachante = True

    # Colaborador com permissão ver_logs_banca
    is_colab_logs = False
    if not is_despachante and not _is_admin_ou_acesso_total(request):
        if request.session.get('tipo_usuario') == 'colaborador' and 'ver_logs_banca' in permissoes:
            cid = request.session.get('colaborador_id')
            col = Colaborador.objects.filter(pk=cid, estado='Ativo').select_related('banca').first()
            if col and col.banca:
                banca = col.banca
                is_colab_logs = True

    if not _is_admin_ou_acesso_total(request) and papel != 'Administrador' and not Usuario.objects.filter(
        pk=usuario_id,
        permissoes_diretas__codigo='acesso_auditoria'
    ).exists() and not Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo='acesso_auditoria'
    ).exists() and not is_despachante and not is_colab_logs:
        messages.error(request, 'Acesso restrito a Administradores, Auditores e Despachantes.')
        return redirect('dashboard')

    accao_filter = request.GET.get('accao', '')
    modulo_filter = request.GET.get('modulo', '')
    busca = request.GET.get('busca', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')

    logs = LogAtividade.objects.all()

    # Filtrar por banca se for despachante ou colaborador com ver_logs_banca
    if (is_despachante or is_colab_logs) and banca:
        logs = logs.filter(banca_id=banca.pk)

    if accao_filter:
        logs = logs.filter(accao=accao_filter)
    if modulo_filter:
        logs = logs.filter(modulo=modulo_filter)
    if busca:
        logs = logs.filter(
            Q(usuario_nome__icontains=busca) |
            Q(email__icontains=busca) |
            Q(descricao__icontains=busca) |
            Q(ip__icontains=busca)
        )
    if data_inicio:
        logs = logs.filter(created_at__gte=data_inicio)
    if data_fim:
        logs = logs.filter(created_at__lte=data_fim + ' 23:59:59')

    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    try:
        page_obj = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    # Despachantes/colaboradores usam o link dentro do RH, por isso active_menu='RH'
    # para manter o submenu RH aberto. Admins/auditores usam o link standalone em Sistema.
    menu_activo = 'RH' if (is_despachante or is_colab_logs) else 'Sistema'
    context = {
        'active_menu': menu_activo,
        'active_sub': 'logs',
        'page_obj': page_obj,
        'accao_filter': accao_filter,
        'modulo_filter': modulo_filter,
        'busca': busca,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'acoes': LogAtividade.ACOES,
        'modulos': LogAtividade.MODULOS,
    }
    context.update({
        'usuario': request.session.get('usuario', {}),
        'papel': papel,
        'nome': request.session.get('usuario', {}).get('nome', ''),
    })
    return render(request, 'users/logs_atividade.html', context)


def manual_utilizador_view(request):
    """Renderiza o Manual do Utilizador SICDOA."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    context = {
        'active_menu': 'Manual',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'nome': request.session.get('usuario', {}).get('nome', ''),
    }
    return render(request, 'manual_sicdoa_web/index.html', context)
