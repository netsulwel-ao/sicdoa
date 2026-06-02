"""
Views de administração do RH — apenas para utilizadores com papel 'Administrador'.
Permite gerir todos os despachantes e as suas bancas.
"""
import json
import bcrypt

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.db import connection
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse

from .acesso import obter_acesso_admin
from .models import Banca, FilialBanca, Colaborador, GestorFilial
from users.models import Usuario
from utils.email_utils import gerar_senha_aleatoria, _enviar


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _requer_admin(fn):
    """Decorator: bloqueia acesso se não for Administrador."""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        if not obter_acesso_admin(request):
            messages.error(request, 'Acesso restrito a Administradores.')
            return redirect('dashboard')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _ctx_admin(request, sub='', extra=None):
    u = request.session.get('usuario', {})
    ctx = {
        'usuario': u,
        'nome': u.get('nome', ''),
        'papel': u.get('papel', ''),
        'active_menu': 'RH',
        'active_sub': sub,
        'is_admin_sistema': True,
    }
    if extra:
        ctx.update(extra)
    return ctx


def _hash_password(senha: str) -> str:
    """Gera hash bcrypt compatível com PHP ($2y$)."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(senha.encode('utf-8'), salt)
    return hashed.decode('utf-8').replace('$2b$', '$2y$')


# ─── Criar Novo Despachante ───────────────────────────────────────────────────

@_requer_admin
def admin_despachante_novo_view(request):
    """Cria um novo despachante no sistema."""
    erros = {}
    form_data = {}

    if request.method == 'POST':
        nome     = request.POST.get('nome', '').strip()
        apelido  = request.POST.get('apelido', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        email    = request.POST.get('email', '').strip().lower()
        nif      = request.POST.get('nif', '').strip()
        cedula   = request.POST.get('cedula', '').strip()
        enviar   = request.POST.get('enviar_credenciais') == '1'

        form_data = {
            'nome': nome, 'apelido': apelido, 'telefone': telefone,
            'email': email, 'nif': nif, 'cedula': cedula,
        }

        # ── Validações ────────────────────────────────────────────────────
        if not nome:
            erros['nome'] = 'O nome é obrigatório.'
        if not apelido:
            erros['apelido'] = 'O apelido é obrigatório.'
        if not email:
            erros['email'] = 'O e-mail é obrigatório.'
        elif Usuario.objects.filter(email=email).exists():
            erros['email'] = 'Já existe um utilizador com este e-mail.'
        if not nif:
            erros['nif'] = 'O NIF é obrigatório.'
        elif Usuario.objects.filter(nif=nif).exists():
            erros['nif'] = 'Já existe um despachante com este NIF.'
        if not cedula:
            erros['cedula'] = 'A cédula é obrigatória.'
        elif Usuario.objects.filter(cedula=cedula).exists():
            erros['cedula'] = 'Já existe um despachante com esta cédula.'

        if not erros:
            # ── Gerar username único ──────────────────────────────────────
            base_username = email.split('@')[0]
            username = base_username
            contador = 1
            while Usuario.objects.filter(username=username).exists():
                username = f'{base_username}{contador}'
                contador += 1

            # ── Gerar senha temporária ────────────────────────────────────
            senha = gerar_senha_aleatoria(10)
            hash_senha = _hash_password(senha)

            # ── Criar utilizador ──────────────────────────────────────────
            nome_completo = f'{nome} {apelido}'.strip()

            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO usuarios
                       (username, password, nome, email, telefone, nif, cedula,
                        papel, status, created_at, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s,
                               'Despachante Oficial', 'Ativo', NOW(), NOW())""",
                    [username, hash_senha, nome_completo, email,
                     telefone, nif, cedula],
                )
                novo_id = cursor.lastrowid

            # ── Foto de perfil ────────────────────────────────────────────
            if 'foto' in request.FILES:
                import os
                from django.conf import settings as django_settings
                foto = request.FILES['foto']
                ext = os.path.splitext(foto.name)[1].lower()
                pasta = os.path.join(django_settings.MEDIA_ROOT, 'funcionarios', 'fotos')
                os.makedirs(pasta, exist_ok=True)
                nome_ficheiro = f'despachante_{novo_id}{ext}'
                caminho = os.path.join(pasta, nome_ficheiro)
                with open(caminho, 'wb+') as dest:
                    for chunk in foto.chunks():
                        dest.write(chunk)
                caminho_relativo = f'funcionarios/fotos/{nome_ficheiro}'
                with connection.cursor() as cursor:
                    cursor.execute(
                        'UPDATE usuarios SET foto = %s WHERE id = %s',
                        [caminho_relativo, novo_id],
                    )

            # ── Enviar credenciais ────────────────────────────────────────
            msg_email = ''
            if enviar:
                novo_usuario = Usuario.objects.get(pk=novo_id)
                sucesso_email, msg_email = _enviar_credenciais_despachante(novo_usuario, senha)
                if sucesso_email:
                    messages.success(
                        request,
                        f'Despachante criado e credenciais enviadas para {email}.',
                    )
                else:
                    messages.warning(
                        request,
                        f'Despachante criado, mas falhou o envio do email: {msg_email}',
                    )
            else:
                messages.success(request, f'Despachante "{nome_completo}" criado com sucesso.')

            return redirect('admin_despachante_detalhe', usuario_id=novo_id)

    ctx = _ctx_admin(request, sub='admin_despachantes', extra={
        'erros': erros,
        'form_data': form_data,
    })
    return render(request, 'rh/admin/despachante_novo.html', ctx)

def _enviar_credenciais_despachante(despachante, senha):
    """Envia email com credenciais de acesso SICDOA ao despachante."""
    from django.conf import settings
    from django.urls import reverse

    base = getattr(settings, 'SITE_URL', 'https://sicdoa-ycg9.onrender.com').rstrip('/')
    link_login = f"{base}{reverse('login')}"

    assunto = 'As suas credenciais de acesso — SICDOA'

    texto = f"""Prezado(a) {despachante.nome},

A sua conta no Sistema SICDOA foi configurada pelo Administrador.

Credenciais de acesso:
  Email : {despachante.email}
  Senha : {senha}

Inicie sessão em: {link_login}

Por segurança, altere a sua senha após o primeiro acesso.

Atenciosamente,
Administração SICDOA — CDOA Angola
"""

    html = f"""
<!DOCTYPE html>
<html lang="pt">
<body style="margin:0;padding:0;background:#f6f7f8;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
  <tr><td align="center" style="padding:40px 20px;">
    <table width="560" cellpadding="0" cellspacing="0"
           style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08);">
      <!-- Header -->
      <tr><td style="background:linear-gradient(135deg,#137fec,#0ea5e9);padding:32px 40px;">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">CDOA Sistema</h1>
        <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px;">Credenciais de Acesso ao SICDOA</p>
      </td></tr>
      <!-- Body -->
      <tr><td style="padding:36px 40px;">
        <p style="margin:0 0 16px;color:#374151;font-size:15px;">
          Prezado(a) <strong>{despachante.nome}</strong>,
        </p>
        <p style="margin:0 0 24px;color:#6b7280;font-size:14px;line-height:1.6;">
          A sua conta no Sistema SICDOA foi configurada. Utilize as credenciais abaixo para aceder à plataforma.
        </p>
        <!-- Credenciais -->
        <table width="100%" cellpadding="0" cellspacing="0"
               style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;margin-bottom:24px;">
          <tr><td style="padding:20px 24px;">
            <p style="margin:0 0 12px;font-size:13px;color:#0369a1;font-weight:600;
                      text-transform:uppercase;letter-spacing:.05em;">As suas credenciais</p>
            <p style="margin:0 0 10px;font-size:14px;color:#374151;">
              <strong>Email:</strong>&nbsp;{despachante.email}
            </p>
            <p style="margin:0;font-size:14px;color:#374151;">
              <strong>Senha:</strong>&nbsp;
              <code style="background:#e0f2fe;padding:3px 10px;border-radius:5px;
                           font-size:15px;letter-spacing:.08em;">{senha}</code>
            </p>
          </td></tr>
        </table>
        <!-- Botão -->
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
          <tr><td align="center">
            <a href="{link_login}"
               style="display:inline-block;background:#137fec;color:#fff;text-decoration:none;
                      font-size:15px;font-weight:600;padding:14px 36px;border-radius:10px;">
              Iniciar sessão no SICDOA
            </a>
          </td></tr>
          <tr><td align="center" style="padding-top:10px;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
              Ou aceda directamente:
              <a href="{link_login}" style="color:#137fec;">{link_login}</a>
            </p>
          </td></tr>
        </table>
        <p style="margin:0;color:#ef4444;font-size:13px;font-weight:600;">
          Por segurança, altere a sua senha após o primeiro acesso.
        </p>
      </td></tr>
      <!-- Footer -->
      <tr><td style="background:#f9fafb;padding:20px 40px;border-top:1px solid #e5e7eb;">
        <p style="margin:0;color:#9ca3af;font-size:12px;">
          © 2026 CDOA Sistema · Câmara dos Despachantes Oficiais de Angola
        </p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""
    return _enviar(assunto, texto, html, despachante.email)


# ─── Lista de Despachantes ────────────────────────────────────────────────────

@_requer_admin
def admin_despachantes_view(request):
    """Lista todos os despachantes (utilizadores com papel Despachante Oficial)."""
    q = request.GET.get('q', '').strip()
    status_filtro = request.GET.get('status', '')

    despachantes = Usuario.objects.filter(papel='Despachante Oficial').order_by('nome')

    if q:
        despachantes = despachantes.filter(
            Q(nome__icontains=q) | Q(email__icontains=q) | Q(nif__icontains=q)
        )
    if status_filtro:
        despachantes = despachantes.filter(status=status_filtro)

    ids = list(despachantes.values_list('id', flat=True))
    bancas = Banca.objects.filter(usuario_id__in=ids).annotate(
        num_colaboradores=Count('colaboradores')
    )
    bancas_por_usuario = {}
    for b in bancas:
        bancas_por_usuario.setdefault(b.usuario_id, []).append(b)

    despachantes_info = []
    for d in despachantes:
        bancas_lista = bancas_por_usuario.get(d.id, [])
        despachantes_info.append({
            'usuario': d,
            'bancas': bancas_lista,
            'total_bancas': len(bancas_lista),
            'total_colaboradores': sum(getattr(b, 'num_colaboradores', 0) for b in bancas_lista),
        })

    paginator = Paginator(despachantes_info, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='admin_despachantes', extra={
        'despachantes_info': page_obj,
        'total_despachantes': len(despachantes_info),
        'page_obj': page_obj,
        'q': q,
        'status_filtro': status_filtro,
    })
    return render(request, 'rh/admin/despachantes_lista.html', ctx)


# ─── Detalhe de Despachante ───────────────────────────────────────────────────

@_requer_admin
def admin_despachante_detalhe_view(request, usuario_id):
    """Detalhe de um despachante: dados pessoais + todas as suas bancas."""
    despachante = get_object_or_404(Usuario, pk=usuario_id, papel='Despachante Oficial')
    bancas = Banca.objects.filter(usuario_id=usuario_id).prefetch_related(
        'filiais', 'colaboradores__filial'
    ).order_by('-criado_em')

    bancas_info = []
    for b in bancas:
        filiais = [f for f in b.filiais.all() if f.ativa]
        filiais.sort(key=lambda x: x.provincia)
        colaboradores = list(b.colaboradores.select_related('filial').all())
        colaboradores.sort(key=lambda x: x.nome)
        bancas_info.append({
            'banca': b,
            'filiais': filiais,
            'colaboradores': colaboradores,
            'total_filiais': len(filiais),
            'total_colaboradores': len(colaboradores),
        })

    ctx = _ctx_admin(request, sub='admin_despachantes', extra={
        'despachante': despachante,
        'bancas_info': bancas_info,
        'total_bancas': len(bancas_info),
        'total_colaboradores': sum(info['total_colaboradores'] for info in bancas_info),
    })
    return render(request, 'rh/admin/despachante_detalhe.html', ctx)


# ─── Editar Despachante ───────────────────────────────────────────────────────

@_requer_admin
def admin_despachante_editar_view(request, usuario_id):
    """Edita os dados de um despachante."""
    despachante = get_object_or_404(Usuario, pk=usuario_id, papel='Despachante Oficial')

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip().lower()
        telefone = request.POST.get('telefone', '').strip()
        nif = request.POST.get('nif', '').strip()
        cedula = request.POST.get('cedula', '').strip()

        erros = []
        if not nome:
            erros.append('O nome é obrigatório.')
        if not email:
            erros.append('O email é obrigatório.')
        elif Usuario.objects.filter(email=email).exclude(pk=usuario_id).exists():
            erros.append('Já existe outro utilizador com este email.')

        if erros:
            for e in erros:
                messages.error(request, e)
        else:
            despachante.nome = nome
            despachante.email = email
            despachante.telefone = telefone
            despachante.nif = nif
            despachante.cedula = cedula
            despachante.save()
            messages.success(request, f'Dados de {nome} actualizados com sucesso.')
            return redirect('admin_despachante_detalhe', usuario_id=usuario_id)

    ctx = _ctx_admin(request, sub='admin_despachantes', extra={
        'despachante': despachante,
    })
    return render(request, 'rh/admin/despachante_editar.html', ctx)


# ─── Bloquear / Desbloquear Despachante ──────────────────────────────────────

@_requer_admin
def admin_despachante_toggle_view(request, usuario_id):
    """Bloqueia (Suspenso) ou desbloqueia (Ativo) um despachante."""
    if request.method != 'POST':
        return redirect('admin_despachantes')

    despachante = get_object_or_404(Usuario, pk=usuario_id, papel='Despachante Oficial')

    if despachante.status == 'Ativo':
        despachante.status = 'Suspenso'
        estado_msg = 'bloqueado'
    else:
        despachante.status = 'Ativo'
        estado_msg = 'desbloqueado'

    despachante.save(update_fields=['status'])
    messages.success(request, f'Despachante "{despachante.nome}" {estado_msg} com sucesso.')
    return redirect('admin_despachante_detalhe', usuario_id=usuario_id)


# ─── Enviar Credenciais ao Despachante ───────────────────────────────────────

@_requer_admin
def admin_despachante_enviar_credenciais_view(request, usuario_id):
    """Gera nova senha e envia credenciais de acesso ao despachante por email."""
    if request.method != 'POST':
        return redirect('admin_despachante_detalhe', usuario_id=usuario_id)

    despachante = get_object_or_404(Usuario, pk=usuario_id, papel='Despachante Oficial')

    if not despachante.email:
        messages.error(request, 'Este despachante não tem email registado.')
        return redirect('admin_despachante_detalhe', usuario_id=usuario_id)

    # Gerar nova senha aleatória
    senha = gerar_senha_aleatoria(10)
    hash_senha = _hash_password(senha)

    # Guardar a nova senha na base de dados
    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE usuarios SET password = %s, updated_at = %s WHERE id = %s',
            [hash_senha, timezone.now(), despachante.id],
        )

    # Enviar email
    sucesso, msg = _enviar_credenciais_despachante(despachante, senha)

    if sucesso:
        messages.success(
            request,
            f'Credenciais enviadas com sucesso para {despachante.email}.',
        )
    else:
        messages.error(request, f'Senha redefinida, mas falhou o envio do email: {msg}')

    return redirect('admin_despachante_detalhe', usuario_id=usuario_id)


# ─── Lista de Bancas ──────────────────────────────────────────────────────────

@_requer_admin
def admin_bancas_view(request):
    """Lista todas as bancas do sistema."""
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '')

    bancas_qs = Banca.objects.order_by('nome')

    if q:
        bancas_qs = bancas_qs.filter(
            Q(nome__icontains=q) | Q(nif__icontains=q) | Q(provincia__icontains=q)
        )
    if estado == 'ativa':
        bancas_qs = bancas_qs.filter(ativa=True)
    elif estado == 'inativa':
        bancas_qs = bancas_qs.filter(ativa=False)

    bancas_qs = bancas_qs.annotate(
        num_colaboradores=Count('colaboradores'),
        num_filiais=Count('filiais'),
    )

    ids_usuarios = list(bancas_qs.values_list('usuario_id', flat=True).distinct())
    usuarios_map = {u.id: u for u in Usuario.objects.filter(id__in=ids_usuarios)}

    bancas_info = []
    for b in bancas_qs:
        bancas_info.append({
            'banca': b,
            'dono': usuarios_map.get(b.usuario_id),
            'total_colaboradores': getattr(b, 'num_colaboradores', 0),
            'total_filiais': getattr(b, 'num_filiais', 0),
        })

    paginator = Paginator(bancas_info, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='admin_bancas', extra={
        'bancas_info': page_obj,
        'total_bancas': len(bancas_info),
        'page_obj': page_obj,
        'q': q,
        'estado': estado,
    })
    return render(request, 'rh/admin/bancas_lista.html', ctx)


# ─── Detalhe de Banca ─────────────────────────────────────────────────────────

@_requer_admin
def admin_banca_detalhe_view(request, banca_id):
    """Detalhe completo de uma banca: filiais, colaboradores, estatísticas."""
    banca = get_object_or_404(Banca.objects.annotate(
        num_filiais=Count('filiais', filter=Q(filiais__ativa=True)),
    ), pk=banca_id)
    dono = Usuario.objects.filter(pk=banca.usuario_id).first()

    filiais = banca.filiais.order_by('provincia')
    colaboradores = banca.colaboradores.select_related('filial').order_by('nome')

    stats = colaboradores.aggregate(
        total_ativos=Count('id', filter=Q(estado='Ativo')),
        total_inativos=Count('id', filter=~Q(estado='Ativo')),
        total_colaboradores=Count('id'),
    )

    ctx = _ctx_admin(request, sub='admin_bancas', extra={
        'banca': banca,
        'dono': dono,
        'filiais': filiais,
        'colaboradores': colaboradores,
        'total_filiais': getattr(banca, 'num_filiais', 0),
        'total_colaboradores': stats['total_colaboradores'],
        'total_ativos': stats['total_ativos'],
        'total_inativos': stats['total_inativos'],
    })
    return render(request, 'rh/admin/banca_detalhe.html', ctx)


# ─── Ativar / Desativar Banca ─────────────────────────────────────────────────

@_requer_admin
def admin_banca_toggle_view(request, banca_id):
    """Ativa ou desativa uma banca."""
    if request.method != 'POST':
        return redirect('admin_bancas')

    banca = get_object_or_404(Banca, pk=banca_id)
    banca.ativa = not banca.ativa
    banca.save(update_fields=['ativa'])

    estado = 'ativada' if banca.ativa else 'desativada'
    messages.success(request, f'Banca "{banca.nome}" {estado} com sucesso.')
    return redirect('admin_banca_detalhe', banca_id=banca_id)


@_requer_admin
def admin_atribuir_cargo_view(request, usuario_id):
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    from .models import CargoMesa
    FUNCOES = [f[0] for f in CargoMesa.FUNCOES]
    cargo_atual = CargoMesa.objects.filter(usuario=usuario).first()

    if request.method == 'POST':
        funcao = request.POST.get('funcao', '').strip()
        if not funcao or funcao not in FUNCOES:
            messages.error(request, 'Selecione um cargo válido.')
            return redirect('admin_atribuir_cargo', usuario_id=usuario_id)

        ocupante_anterior = CargoMesa.objects.filter(funcao=funcao).exclude(usuario=usuario).first()
        if ocupante_anterior:
            nome_anterior = ocupante_anterior.usuario.nome
            ocupante_anterior.delete()
            _criar_notificacao(ocupante_anterior.usuario.id, 'cargo_mesa_removido',
                f'Cargo removido: {funcao}',
                f'Foi removido do cargo de {funcao} da Mesa porque {usuario.nome} foi designado.',
                '/rh/admin/despachantes/')

        CargoMesa.objects.update_or_create(
            usuario=usuario,
            defaults={'funcao': funcao, 'atribuido_em': timezone.now()}
        )

        is_secretario = funcao in ('1º Secretário', '2º Secretário', 'Secretário')
        is_vice = 'Vice-Presidente' in funcao
        usuario.is_secretario = is_secretario
        usuario.is_vice_secretario = is_vice
        usuario.save(update_fields=['is_secretario', 'is_vice_secretario'])

        _criar_notificacao(usuario.id, 'cargo_mesa_atribuido',
            f'Novo cargo: {funcao}',
            f'Foi designado como {funcao} da Mesa.',
            '/governanca/secretario/')

        if request.session.get('usuario_id') == usuario.id:
            sessao = request.session['usuario']
            sessao['is_secretario'] = usuario.is_secretario
            sessao['is_vice_secretario'] = usuario.is_vice_secretario
            request.session.modified = True

        messages.success(request, f'{usuario.nome} agora é {funcao} da Mesa.')
        return redirect('admin_despachantes')

    ocupantes = {c.funcao: c.usuario.nome for c in CargoMesa.objects.select_related('usuario').all()}
    ctx = _ctx_admin(request, sub='admin_despachantes', extra={
        'usuario_alvo': usuario,
        'cargo_atual': cargo_atual.funcao if cargo_atual else None,
        'ocupantes': ocupantes,
        'funcoes': CargoMesa.FUNCOES,
    })
    return render(request, 'rh/admin/atribuir_cargo.html', ctx)


def _criar_notificacao(usuario_id, tipo, titulo, mensagem, link):
    from governanca.models import Notificacao
    Notificacao.objects.create(
        usuario_id=usuario_id, tipo=tipo,
        titulo=titulo, mensagem=mensagem, link=link,
    )
