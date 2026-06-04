"""Views do módulo users — autenticação, dashboards e portal do colaborador."""
# pylint: disable=no-member
import json
import smtplib
import ssl as ssl_lib
from datetime import date

import bcrypt
import requests
import urllib3
from utils.ssl_utils import requests_kwargs_ssl

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
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
    sessao_expirada,
    tempo_restante_sessao,
)
from .models import Usuario


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
    try:
        return Colaborador.objects.get(id=colaborador_id), None
    except Colaborador.DoesNotExist:
        return None, redirect("login")


# ─── Autenticação ─────────────────────────────────────────────────────────────

def login_view(request):
    """Página de login — autentica utilizadores e colaboradores."""
    if request.session.get("usuario_id"):
        if not sessao_expirada(request):
            return redirect("dashboard")
        limpar_sessao(request)

    if request.method != "POST":
        return render(request, "login.html")

    email = request.POST.get("email", "").strip().lower()
    senha = request.POST.get("password", "").strip()

    if not email or not senha:
        messages.error(request, "Preencha todos os campos.")
        return render(request, "login.html")

    usuario = None
    tipo_usuario = None
    usuario_bloqueado = False

    # 1. Tentar na tabela usuarios
    try:
        u = Usuario.objects.get(email=email)
        
        # Verificar se está bloqueado
        if u.status == 'Suspenso':
            usuario_bloqueado = True
            messages.error(
                request,
                "A sua conta está bloqueada. Entre em contacto com o Administrador do sistema para reactivar o seu acesso."
            )
            return render(request, "login.html")
        
        # Verificar se está inativo
        if u.status == 'Inativo':
            messages.error(
                request,
                "A sua conta está inativa. Entre em contacto com o Administrador do sistema."
            )
            return render(request, "login.html")
        
        # Verificar senha apenas se status='Ativo'
        if u.status == "Ativo" and _verificar_password(senha, u.password):
            usuario = u
            tipo_usuario = "usuario"
    except Usuario.DoesNotExist:
        pass

    # 2. Tentar na tabela colaboradores
    if not usuario and not usuario_bloqueado:
        try:
            col = Colaborador.objects.get(email=email, estado="Ativo")
            if col.password and _verificar_password(senha, col.password):
                tipo_usuario = "colaborador"

                class _UsuarioColaborador:  # noqa: R0903
                    def __init__(self, c):
                        self.id = c.id
                        self.nome = c.nome
                        self.email = c.email
                        self.papel = "Colaborador"
                        self.nif = c.nif
                        self.cedula = c.bi
                        self.telefone = c.telefone
                        self.username = c.email
                        self.tipo = "colaborador"
                        self.colaborador_id = c.id

                usuario = _UsuarioColaborador(col)
        except Colaborador.DoesNotExist:
            pass

    if not usuario:
        messages.error(request, "❌ Credenciais inválidas. Verifique o seu email e senha.")
        return render(request, "login.html")

    criar_sessao_usuario(request, usuario)

    if tipo_usuario == "usuario":
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE usuarios SET ultimo_acesso = %s WHERE id = %s",
                [timezone.now(), usuario.id],
            )

    messages.success(request, f"Bem-vindo(a) {usuario.nome}!")
    if tipo_usuario == "colaborador":
        return redirect("dashboard_colaborador")
    return redirect("dashboard")


@csrf_exempt
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
        return JsonResponse({
            'success': False,
            'message': f'Erro interno: {str(e)}'
        }, status=500)


def logout_view(request):
    """Termina a sessão e redireciona para o login."""
    limpar_sessao(request)
    messages.info(request, "Sessão terminada com sucesso. Até logo!")
    return redirect("login")


# ─── Dashboards ───────────────────────────────────────────────────────────────

def dashboard_view(request):
    """Dashboard principal para utilizadores do sistema."""
    if not request.session.get("usuario_id"):
        return redirect("login")
    if sessao_expirada(request):
        limpar_sessao(request)
        return redirect("login")

    usuario = request.session["usuario"]
    uid     = request.session["usuario_id"]
    papel   = usuario.get("papel", "")

    from aduaneiro.models import DeclaracaoUnica
    from django.utils import timezone as tz
    from django.db.models import Sum

    # DUs do utilizador (ou todas se Admin)
    if papel == "Administrador":
        dus_qs = DeclaracaoUnica.objects.all()
    else:
        dus_qs = DeclaracaoUnica.objects.filter(usuario_id=uid)

    # Processos ativos = Rascunho + Submetida + Em Análise
    dus_ativas = dus_qs.filter(
        status__in=["Rascunho", "Submetida", "Em Análise"]
    ).order_by("-created_at")

    paginator = Paginator(dus_ativas, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Contadores para os cards
    total_ativos    = dus_qs.filter(status__in=["Rascunho", "Submetida", "Em Análise"]).count()
    total_concluidos = dus_qs.filter(
        status="Aprovada",
        created_at__month=tz.now().month,
        created_at__year=tz.now().year,
    ).count()
    total_geral_mes = dus_qs.filter(
        created_at__month=tz.now().month,
        created_at__year=tz.now().year,
    ).aggregate(total=Sum('total_geral'))['total'] or 0

    return render(request, "dashbord.html", {
        "usuario": usuario,
        "nome": usuario["nome"],
        "papel": usuario["papel"],
        "active_menu": "Dashboard",
        "tempo_restante_sessao": tempo_restante_sessao(request),
        "dus_ativas": page_obj,
        "page_obj": page_obj,
        "total_ativos": total_ativos,
        "total_concluidos": total_concluidos,
        "total_geral_mes": total_geral_mes,
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

    colaborador_id = request.session.get("colaborador_id")
    colaborador = Colaborador.objects.get(id=colaborador_id)

    contexto = {
        "usuario": request.session["usuario"],
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Dashboard",
        "tempo_restante_sessao": tempo_restante_sessao(request),
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
    }

    template = (
        "colaboradores/responsavel_dashboard.html"
        if colaborador.e_gestor_filial
        else "colaboradores/dashboard.html"
    )
    return render(request, template, contexto)


# ─── Utilitário de teste de email ─────────────────────────────────────────────

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
    """Perfil do colaborador — editar telefone e palavra-passe."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    if request.method == "POST":
        acao = request.POST.get("acao", "")

        if acao == "editar_perfil":
            colaborador.telefone = request.POST.get("telefone", "").strip()
            colaborador.save(update_fields=["telefone"])
            messages.success(request, "Perfil actualizado com sucesso.")
            return redirect("colaborador_perfil")

        if acao == "alterar_password":
            senha_actual = request.POST.get("senha_actual", "")
            nova_senha = request.POST.get("nova_senha", "")
            confirmar = request.POST.get("confirmar_senha", "")

            if not colaborador.password:
                messages.error(request, "Não tem palavra-passe definida. Contacte o RH.")
            elif not _verificar_password(senha_actual, colaborador.password):
                messages.error(request, "A palavra-passe actual está incorrecta.")
            elif len(nova_senha) < 4:
                messages.error(request, "A nova palavra-passe deve ter pelo menos 4 caracteres.")
            elif nova_senha != confirmar:
                messages.error(request, "As palavras-passe não coincidem.")
            else:
                colaborador.password = _hash_password(nova_senha)
                colaborador.save(update_fields=["password"])
                messages.success(request, "Palavra-passe alterada com sucesso.")
                return redirect("colaborador_perfil")

    return render(request, "colaboradores/perfil.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Meus Dados",
        "active_sub": "perfil",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
    })


def documentos_view(request):
    """Documentos do colaborador."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    documentos = DocumentoColaborador.objects.filter(
        colaborador=colaborador
    ).order_by("-criado_em")

    paginator = Paginator(documentos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "colaboradores/documentos.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Meus Dados",
        "active_sub": "documentos",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "documentos": page_obj,
        "page_obj": page_obj,
    })


def presenca_view(request):
    """Marcar presença — regista entrada ou saída do dia."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    hoje = timezone.localdate()
    registo_hoje = RegistoPresenca.objects.filter(
        colaborador=colaborador, data=hoje
    ).first()

    if request.method == "POST":
        acao = request.POST.get("acao")
        agora = timezone.localtime(timezone.now()).time()

        if acao == "entrada":
            if registo_hoje:
                messages.error(request, "Já registou a entrada hoje.")
            else:
                RegistoPresenca.objects.create(
                    colaborador=colaborador,
                    data=hoje,
                    tipo="Entrada",
                    hora_entrada=agora,
                    estado="Pendente",
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

    historico_qs = RegistoPresenca.objects.filter(
        colaborador=colaborador
    ).order_by("-data")

    paginator = Paginator(historico_qs, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "colaboradores/presenca.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Presença",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "hoje": hoje,
        "registo_hoje": registo_hoje,
        "historico": page_obj,
        "page_obj": page_obj,
    })


def salario_view(request):
    """Processo salarial — 8 recibos por página, mais recente primeiro."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    todos = ReciboSalarial.objects.filter(
        colaborador=colaborador
    ).select_related("processamento").order_by(
        "-processamento__ano", "-processamento__mes"
    )

    paginator = Paginator(todos, 8)
    try:
        pagina_num = int(request.GET.get("pagina", 1))
    except (ValueError, TypeError):
        pagina_num = 1
    pagina = paginator.get_page(pagina_num)

    return render(request, "colaboradores/salario.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Salarial",
        "active_sub": "salario",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "recibos": pagina,
        "paginator": paginator,
        "pagina_actual": pagina_num,
        "recibo_mais_recente": todos.first(),
        "total_recibos": todos.count(),
        "salario_base": colaborador.salario_base or 0,
    })


def historico_salarial_view(request):
    """Histórico salarial completo — 8 por página."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    todos = ReciboSalarial.objects.filter(
        colaborador=colaborador
    ).select_related("processamento").order_by(
        "-processamento__ano", "-processamento__mes"
    )

    paginator = Paginator(todos, 8)
    try:
        pagina_num = int(request.GET.get("pagina", 1))
    except (ValueError, TypeError):
        pagina_num = 1
    pagina = paginator.get_page(pagina_num)

    return render(request, "colaboradores/historico_salarial.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Salarial",
        "active_sub": "historico-salarial",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "recibos": pagina,
        "paginator": paginator,
        "pagina_actual": pagina_num,
        "total_recibos": todos.count(),
        "salario_base": colaborador.salario_base or 0,
    })


def ferias_view(request):
    """Pedido de férias — submete e lista pedidos anteriores."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

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
                elif PedidoFerias.objects.filter(
                    colaborador=colaborador,
                    estado__in=["Pendente", "Aprovado"],
                    data_inicio__lte=data_fim,
                    data_fim__gte=data_inicio,
                ).exists():
                    messages.error(request, "Já existe um pedido de férias nesse período.")
                else:
                    PedidoFerias.objects.create(
                        colaborador=colaborador,
                        data_inicio=data_inicio,
                        data_fim=data_fim,
                        motivo=motivo,
                        estado="Pendente",
                    )
                    messages.success(
                        request,
                        "Pedido de férias submetido com sucesso. Aguarde aprovação.",
                    )
                    return redirect("colaborador_ferias")
            except ValueError:
                messages.error(request, "Datas inválidas.")

    pedidos = PedidoFerias.objects.filter(
        colaborador=colaborador
    ).order_by("-criado_em")

    paginator = Paginator(pedidos, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, "colaboradores/ferias.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Ferias",
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
        "pedidos": page_obj,
        "page_obj": page_obj,
    })


def buscar_view(request):
    """Resultados de busca para colaboradores."""
    colaborador, erro = _verificar_sessao_colaborador(request)
    if erro:
        return erro

    query = request.GET.get("q", "").strip()
    if not query:
        return redirect("dashboard_colaborador")

    return render(request, "colaboradores/buscar.html", {
        "nome": colaborador.nome,
        "papel": "Colaborador",
        "active_menu": "Dashboard",
        "query": query,
        "colaborador": colaborador,
        "e_responsavel": colaborador.e_gestor_filial,
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

    from users.models import UsuarioCargo
    vinculo = UsuarioCargo.objects.filter(usuario=usuario).select_related('cargo', 'atribuido_por').first()
    cargo_info = None
    if vinculo:
        cargo_info = {
            'nome': vinculo.cargo.nome,
            'slug': vinculo.cargo.slug,
            'descricao': vinculo.cargo.descricao,
            'atribuido_em': vinculo.atribuido_em,
            'atribuido_por': vinculo.atribuido_por.nome if vinculo.atribuido_por else None,
        }

    from aduaneiro.models import DeclaracaoUnica
    total_dus   = DeclaracaoUnica.objects.filter(usuario_id=usuario.id).count()
    dus_mes     = DeclaracaoUnica.objects.filter(
        usuario_id=usuario.id,
        created_at__month=timezone.now().month,
        created_at__year=timezone.now().year,
    ).count()

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
            "password": usuario.password,
        },
        "cargo_info": cargo_info,
        "tem_senha": bool(usuario.password),
        "nome": usuario.nome,
        "papel": usuario.papel,
        "active_menu": "Perfil",
        "total_dus": total_dus,
        "dus_mes": dus_mes,
        "messages": messages.get_messages(request),
    })


def meu_perfil_guardar(request):
    """Guarda alterações ao perfil via POST — nome, username e telefone."""
    usuario, erro = _verificar_sessao_usuario(request)
    if erro:
        return erro
    if request.method != "POST":
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
    
    if len(nova_senha) < 4:
        messages.error(request, "A nova senha deve ter pelo menos 4 caracteres.")
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
