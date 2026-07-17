"""
Views de administração do RH — apenas para utilizadores com papel 'Administrador'.
Permite gerir todos os despachantes e as suas bancas.
"""
import json

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
from .tax_utils import _hash_password
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


def _requer_admin_ou_permissoes(*perm_codigos):
    """Decorator: permite Administradores OU utilizadores com pelo menos uma das permissões indicadas."""
    def decorator(fn):
        def wrapper(request, *args, **kwargs):
            if not request.session.get('usuario_id'):
                return redirect('login')
            papel = request.session.get('usuario', {}).get('papel', '')
            from users.permissoes import _is_admin_ou_acesso_total
            if _is_admin_ou_acesso_total(request):
                return fn(request, *args, **kwargs)
            from users.permissoes import usuario_tem_permissao
            for codigo in perm_codigos:
                if usuario_tem_permissao(request, codigo):
                    return fn(request, *args, **kwargs)
            messages.error(request, 'Não tem permissão para aceder a esta página.')
            return redirect('dashboard')
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


def _ctx_admin(request, sub='', extra=None, active_menu='ADMIN_RH'):
    u = request.session.get('usuario', {})
    from users.permissoes import get_usuario_permissoes
    user_permissoes = get_usuario_permissoes(request)
    ctx = {
        'usuario': u,
        'nome': u.get('nome', ''),
        'papel': u.get('papel', ''),
        'active_menu': active_menu,
        'active_sub': sub,
        'is_admin_sistema': True,
        'user_permissoes': user_permissoes,
    }
    if extra:
        ctx.update(extra)
    return ctx


# _hash_password imported from tax_utils

# ─── Criar Novo Despachante ───────────────────────────────────────────────────

@_requer_admin
def admin_despachante_novo_view(request):
    return redirect('governanca_utilizador_novo')

def _enviar_credenciais_despachante(despachante, senha):
    """Envia email com credenciais de acesso SICDOA ao despachante."""
    if not despachante.email:
        return False, "Despachante não tem email registado"
    from django.conf import settings
    from django.urls import reverse

    base = settings.SITE_URL.rstrip('/')
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
    from django.shortcuts import redirect
    return redirect('governanca_gerir_utilizadores')


# ─── Detalhe de Despachante ───────────────────────────────────────────────────

@_requer_admin
def admin_despachante_detalhe_view(request, usuario_id):
    return redirect('governanca_utilizador_editar', usuario_id=usuario_id)


# ─── Editar Despachante ───────────────────────────────────────────────────────

@_requer_admin
def admin_despachante_editar_view(request, usuario_id):
    return redirect('governanca_utilizador_editar', usuario_id=usuario_id)


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

    filiais = banca.filiais.annotate(
        num_colaboradores=Count('colaboradores')
    ).order_by('provincia')
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
    foi_ativada = not banca.ativa
    banca.ativa = foi_ativada
    banca.save(update_fields=['ativa'])

    estado = 'ativada' if banca.ativa else 'desativada'
    messages.success(request, f'Banca "{banca.nome}" {estado} com sucesso.')

    # Notificar o dono da banca quando for desativada
    if not banca.ativa:
        dono = Usuario.objects.filter(pk=banca.usuario_id).first()
        if dono:
            _criar_notificacao(
                usuario_id=dono.id,
                tipo='estado_suspenso',
                titulo='Banca Bloqueada',
                mensagem=f'A sua banca "{banca.nome}" foi bloqueada pelo administrador. Entre em contacto para regularizar a situação.',
                link='/rh/banca/',
            )
            # Enviar email
            if dono.email:
                _enviar(
                    assunto='Banca Bloqueada — CDOA',
                    texto=f'Olá {dono.nome},\n\nA sua banca "{banca.nome}" foi bloqueada pelo administrador do sistema. Para regularizar a situação, entre em contacto com a administração do CDOA.\n\nAtenciosamente,\nEquipa CDOA',
                    html=f'<p>Olá <strong>{dono.nome}</strong>,</p><p>A sua banca <strong>"{banca.nome}"</strong> foi bloqueada pelo administrador do sistema.</p><p>Para regularizar a situação, entre em contacto com a administração do CDOA.</p><p>Atenciosamente,<br>Equipa CDOA</p>',
                    destinatarios=[dono.email],
                )

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


# ═══════════════════════════════════════════════════════════════════════════════
# COLABORADORES INSTITUCIONAIS (Equipa do Administrador)
# ═══════════════════════════════════════════════════════════════════════════════

from users.models import (
    ColaboradorInstitucional, Usuario,
    PresencaInstitucional, FeriasInstitucional,
    CicloAvaliacaoInstitucional, AvaliacaoInstitucional,
    ProcessamentoSalarialInstitucional, ReciboSalarialInstitucional,
)


@_requer_admin_ou_permissoes('gerir_colaboradores_inst')
def admin_colaboradores_inst_view(request):
    q = request.GET.get('q', '').strip()
    area = request.GET.get('area', '').strip()

    colaboradores = ColaboradorInstitucional.objects.all().order_by('nome')
    if q:
        colaboradores = colaboradores.filter(nome__icontains=q)
    if area:
        colaboradores = colaboradores.filter(area_actuacao=area)

    paginator = Paginator(colaboradores, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='colaboradores_inst', active_menu='RH_INST', extra={
        'colaboradores': page_obj,
        'total': colaboradores.count(),
        'page_obj': page_obj,
        'q': q,
        'area': area,
        'areas': ColaboradorInstitucional.AREAS,
    })
    return render(request, 'rh/admin/colaboradores_inst_lista.html', ctx)


@_requer_admin_ou_permissoes('gerir_colaboradores_inst')
def admin_colaborador_inst_editar_view(request, pk):
    colaborador = get_object_or_404(ColaboradorInstitucional, pk=pk)

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        area_actuacao = request.POST.get('area_actuacao', '').strip()
        salario_base = request.POST.get('salario_base', '').strip()
        observacoes = request.POST.get('observacoes', '').strip()

        if nome:
            colaborador.nome = nome
            colaborador.email = email
            colaborador.telefone = telefone
            colaborador.area_actuacao = area_actuacao
            if salario_base:
                from decimal import Decimal
                from utils.format_kz import parse_kz
                try:
                    parsed = parse_kz(salario_base)
                    colaborador.salario_base = Decimal(parsed) if parsed else None
                except Exception:
                    colaborador.salario_base = None
            colaborador.observacoes = observacoes
            colaborador.save()
            # Sync usuario
            if colaborador.usuario:
                colaborador.usuario.nome = nome
                colaborador.usuario.email = email if email else colaborador.usuario.email
                colaborador.usuario.telefone = telefone
                colaborador.usuario.save(update_fields=['nome', 'email', 'telefone', 'updated_at'])
            messages.success(request, f'Colaborador "{nome}" atualizado.')
            return redirect('rh_admin_colaboradores_inst')

    ctx = _ctx_admin(request, sub='colaboradores_inst', active_menu='RH_INST', extra={
        'colaborador': colaborador,
    })
    return render(request, 'rh/admin/colaborador_inst_editar.html', ctx)


@_requer_admin_ou_permissoes('gerir_presencas_inst')
def admin_presencas_inst_view(request):
    colaboradores = ColaboradorInstitucional.objects.all().order_by('nome')
    presencas = PresencaInstitucional.objects.all().select_related('colaborador').order_by('-data', '-id')

    q = request.GET.get('q', '').strip()
    data_inicio = request.GET.get('data_inicio', '').strip()
    data_fim = request.GET.get('data_fim', '').strip()
    estado = request.GET.get('estado', '').strip()

    if q:
        presencas = presencas.filter(colaborador__nome__icontains=q)
    if data_inicio:
        presencas = presencas.filter(data__gte=data_inicio)
    if data_fim:
        presencas = presencas.filter(data__lte=data_fim)
    if estado:
        presencas = presencas.filter(estado=estado)

    paginator = Paginator(presencas, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='presencas_inst', active_menu='RH_INST', extra={
        'presencas': page_obj,
        'page_obj': page_obj,
        'colaboradores': colaboradores,
        'q': q,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'estado': estado,
    })
    return render(request, 'rh/admin/presencas_inst_lista.html', ctx)


@_requer_admin_ou_permissoes('gerir_presencas_inst')
def admin_presenca_inst_registar_view(request):
    if request.method == 'POST':
        colaborador_id = request.POST.get('colaborador')
        data = request.POST.get('data')
        tipo = request.POST.get('tipo', 'Entrada')
        hora_entrada = request.POST.get('hora_entrada', '') or None
        hora_saida = request.POST.get('hora_saida', '') or None
        justificacao = request.POST.get('justificacao', '').strip()

        if not colaborador_id or not data:
            messages.error(request, 'Colaborador e data são obrigatórios.')
            return redirect('rh_admin_presencas_inst')

        PresencaInstitucional.objects.create(
            colaborador_id=colaborador_id, data=data, tipo=tipo,
            hora_entrada=hora_entrada, hora_saida=hora_saida,
            justificacao=justificacao, estado='Aprovado',
        )
        messages.success(request, 'Presença registada com sucesso.')
        return redirect('rh_admin_presencas_inst')

    ctx = _ctx_admin(request, sub='presencas_inst', active_menu='RH_INST', extra={
        'colaboradores': ColaboradorInstitucional.objects.filter(estado='Ativo'),
    })
    return render(request, 'rh/admin/presenca_inst_registar.html', ctx)


@_requer_admin_ou_permissoes('gerir_presencas_inst')
def admin_presenca_inst_aprovar_view(request, pk):
    if request.method != 'POST':
        return redirect('rh_admin_presencas_inst')
    presenca = get_object_or_404(PresencaInstitucional, pk=pk)
    acao = request.POST.get('acao', 'aprovar')
    if acao == 'aprovar':
        presenca.estado = 'Aprovado'
        presenca.save(update_fields=['estado'])
        messages.success(request, 'Presença aprovada.')
    elif acao == 'rejeitar':
        presenca.estado = 'Rejeitado'
        presenca.save(update_fields=['estado'])
        messages.success(request, 'Presença rejeitada.')
    return redirect('rh_admin_presencas_inst')


@_requer_admin_ou_permissoes('gerir_ferias_inst')
def admin_ferias_inst_view(request):
    pedidos = FeriasInstitucional.objects.all().select_related('colaborador').order_by('-criado_em')

    estado = request.GET.get('estado', '').strip()
    if estado:
        pedidos = pedidos.filter(estado=estado)

    paginator = Paginator(pedidos, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='ferias_inst', active_menu='RH_INST', extra={
        'pedidos': page_obj,
        'page_obj': page_obj,
        'estado': estado,
    })
    return render(request, 'rh/admin/ferias_inst_lista.html', ctx)


@_requer_admin_ou_permissoes('gerir_ferias_inst')
def admin_ferias_inst_acao_view(request, pk):
    if request.method != 'POST':
        return redirect('rh_admin_ferias_inst')
    pedido = get_object_or_404(FeriasInstitucional, pk=pk)
    acao = request.POST.get('acao', '')
    if acao == 'aprovar':
        pedido.estado = 'Aprovado'
        pedido.save(update_fields=['estado'])
        messages.success(request, 'Pedido de férias aprovado.')
    elif acao == 'rejeitar':
        pedido.estado = 'Rejeitado'
        pedido.save(update_fields=['estado'])
        messages.success(request, 'Pedido de férias rejeitado.')
    return redirect('rh_admin_ferias_inst')


@_requer_admin_ou_permissoes('gerir_avaliacoes_inst')
def admin_avaliacoes_inst_view(request):
    ciclos = CicloAvaliacaoInstitucional.objects.all().order_by('-periodo_inicio')

    paginator = Paginator(ciclos, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='avaliacoes_inst', active_menu='RH_INST', extra={
        'ciclos': page_obj,
        'page_obj': page_obj,
    })
    return render(request, 'rh/admin/avaliacoes_inst_lista.html', ctx)


@_requer_admin_ou_permissoes('gerir_avaliacoes_inst')
def admin_ciclo_inst_novo_view(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        periodo_inicio = request.POST.get('periodo_inicio', '').strip()
        periodo_fim = request.POST.get('periodo_fim', '').strip()

        if not nome or not periodo_inicio or not periodo_fim:
            messages.error(request, 'Todos os campos são obrigatórios.')
            return redirect('rh_admin_avaliacoes_inst')

        CicloAvaliacaoInstitucional.objects.create(
            nome=nome, periodo_inicio=periodo_inicio, periodo_fim=periodo_fim,
        )
        messages.success(request, 'Ciclo de avaliação criado.')
        return redirect('rh_admin_avaliacoes_inst')

    ctx = _ctx_admin(request, sub='avaliacoes_inst', active_menu='RH_INST')
    return render(request, 'rh/admin/ciclo_inst_novo.html', ctx)


@_requer_admin_ou_permissoes('gerir_avaliacoes_inst')
def admin_avaliacao_inst_nova_view(request, ciclo_pk, col_pk=None):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
    avaliacao = None
    if col_pk:
        avaliacao = get_object_or_404(AvaliacaoInstitucional, ciclo=ciclo, colaborador_id=col_pk)

    if request.method == 'POST':
        colaborador_id = request.POST.get('colaborador', col_pk)
        if not colaborador_id:
            messages.error(request, 'Selecione um colaborador.')
            return redirect('rh_admin_avaliacao_inst_nova', ciclo_pk=ciclo_pk)

        defaults = {
            'pontualidade': int(request.POST.get('pontualidade', 3)),
            'produtividade': int(request.POST.get('produtividade', 3)),
            'qualidade_trabalho': int(request.POST.get('qualidade_trabalho', 3)),
            'trabalho_equipa': int(request.POST.get('trabalho_equipa', 3)),
            'iniciativa': int(request.POST.get('iniciativa', 3)),
            'nota_global': request.POST.get('nota_global', 3),
            'pontos_fortes': request.POST.get('pontos_fortes', '').strip(),
            'pontos_melhoria': request.POST.get('pontos_melhoria', '').strip(),
            'plano_desenvolvimento': request.POST.get('plano_desenvolvimento', '').strip(),
        }

        if avaliacao:
            for k, v in defaults.items():
                setattr(avaliacao, k, v)
            avaliacao.save()
            messages.success(request, 'Avaliação atualizada.')
        else:
            AvaliacaoInstitucional.objects.create(ciclo=ciclo, colaborador_id=colaborador_id, **defaults)
            messages.success(request, 'Avaliação registada.')
        return redirect('rh_admin_avaliacoes_inst')

    colaboradores = ColaboradorInstitucional.objects.filter(estado='Ativo')
    ja_avaliados = AvaliacaoInstitucional.objects.filter(ciclo=ciclo).values_list('colaborador_id', flat=True)

    ctx = _ctx_admin(request, sub='avaliacoes_inst', active_menu='RH_INST', extra={
        'ciclo': ciclo,
        'avaliacao': avaliacao,
        'colaboradores': colaboradores,
        'ja_avaliados': list(ja_avaliados),
        'col_pk': col_pk,
    })
    return render(request, 'rh/admin/avaliacao_inst_form.html', ctx)


@_requer_admin_ou_permissoes('processar_salarios_inst')
def admin_salarios_inst_view(request):
    processamentos = ProcessamentoSalarialInstitucional.objects.annotate(
        total_recibos=Count('recibos'),
    ).order_by('-ano', '-mes')

    paginator = Paginator(processamentos, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_admin(request, sub='salarios_inst', active_menu='RH_INST', extra={
        'processamentos': page_obj,
        'page_obj': page_obj,
    })
    return render(request, 'rh/admin/salarios_inst_lista.html', ctx)


@_requer_admin_ou_permissoes('processar_salarios_inst')
def admin_salario_inst_novo_view(request):
    from users.models import (
        ColaboradorInstitucional, ProcessamentoSalarialInstitucional,
        ReciboSalarialInstitucional, SubsidioInstitucional,
        SubsidioReciboInstitucional, PresencaInstitucional,
    )
    from .tax_utils import _calcular_irt, MESES, _dec
    from decimal import Decimal

    if request.method == 'POST':
        mes = int(request.POST.get('mes') or 1)
        ano = int(request.POST.get('ano') or timezone.now().year)
        proc, criado = ProcessamentoSalarialInstitucional.objects.get_or_create(
            mes=mes, ano=ano, defaults={'estado': 'Rascunho'}
        )
        if not criado:
            return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)

        subsidios_inst = list(SubsidioInstitucional.objects.filter(ativo=True))
        subsidio_colab_ids = {}
        for s in subsidios_inst:
            if s.apenas_especificos:
                subsidio_colab_ids[s.pk] = set(s.colaboradores_especificos.values_list('id', flat=True))

        colaboradores_ids = request.POST.getlist('colaboradores')
        colaboradores_qs = ColaboradorInstitucional.objects.filter(estado='Ativo')
        if colaboradores_ids:
            colaboradores_qs = colaboradores_qs.filter(pk__in=colaboradores_ids)
        for col in colaboradores_qs:
            salario = col.salario_base or Decimal('0')
            faltas = PresencaInstitucional.objects.filter(
                colaborador=col, data__month=mes, data__year=ano,
                tipo__in=['Falta', 'Falta_Justificada'], estado='Aprovado',
            ).count()
            dias_uteis = Decimal('22')
            desconto_faltas = (salario / dias_uteis * faltas).quantize(Decimal('0.01')) if faltas > 0 else Decimal('0')
            salario_apos_faltas = max(salario - desconto_faltas, Decimal('0'))
            irt = _calcular_irt(salario_apos_faltas)
            inss_trab = (salario_apos_faltas * Decimal('0.03')).quantize(Decimal('0.01'))
            inss_ent = (salario_apos_faltas * Decimal('0.08')).quantize(Decimal('0.01'))

            subsidios_aplicaveis = []
            for subsidio in subsidios_inst:
                if subsidio.apenas_especificos:
                    if col.id in subsidio_colab_ids.get(subsidio.pk, set()):
                        subsidios_aplicaveis.append(subsidio)
                else:
                    subsidios_aplicaveis.append(subsidio)

            total_subsidios = Decimal('0')
            for subsidio in subsidios_aplicaveis:
                if subsidio.tipo_calculo == 'PERCENTUAL':
                    if subsidio.percentual and salario:
                        total_subsidios += (salario * subsidio.percentual) / 100
                    else:
                        total_subsidios += subsidio.valor_padrao
                elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                    total_subsidios += subsidio.valor_padrao * 22
                elif subsidio.tipo_calculo == 'DEPENDENTES':
                    total_subsidios += subsidio.valor_padrao * 1
                else:
                    total_subsidios += subsidio.valor_padrao

            recibo, recibo_criado = ReciboSalarialInstitucional.objects.get_or_create(
                processamento=proc, colaborador=col,
                defaults={
                    'salario_base': salario,
                    'subsidio_alimentacao': Decimal('0'),
                    'subsidio_transporte': Decimal('0'),
                    'outros_subsidios': total_subsidios,
                    'outros_descontos': desconto_faltas,
                    'irt': irt,
                    'inss_trabalhador': inss_trab,
                    'inss_entidade': inss_ent,
                }
            )

            if recibo_criado:
                for subsidio in subsidios_aplicaveis:
                    if subsidio.tipo_calculo == 'PERCENTUAL':
                        v = (salario * subsidio.percentual) / 100 if subsidio.percentual and salario else subsidio.valor_padrao
                    elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                        v = subsidio.valor_padrao * 22
                    elif subsidio.tipo_calculo == 'DEPENDENTES':
                        v = subsidio.valor_padrao * 1
                    else:
                        v = subsidio.valor_padrao
                    SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=recibo, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )

        return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)

    hoje = timezone.now().date()
    cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
    anos = list(range(2023, hoje.year + 2))
    ctx = _ctx_admin(request, sub='salarios_inst', active_menu='RH_INST', extra={
        'colaboradores': cols, 'meses': list(enumerate(MESES, 1)),
        'anos': anos, 'ano_atual': hoje.year,
    })
    return render(request, 'rh/admin/salario_inst_novo.html', ctx)


@_requer_admin_ou_permissoes('processar_salarios_inst')
def admin_salario_inst_detalhe_view(request, pk):
    from users.models import (
        ProcessamentoSalarialInstitucional, SubsidioInstitucional,
        SubsidioReciboInstitucional,
    )
    from .tax_utils import _calcular_irt, MESES, _dec
    from decimal import Decimal

    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    if request.method == 'POST':
        if proc.estado == 'Pago':
            messages.error(request, 'Processamento Pago não pode ser alterado.')
            return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)

        action = request.POST.get('accao', '')
        if action == 'salvar':
            subsidios_ativos = list(SubsidioInstitucional.objects.filter(ativo=True))
            for r in recibos:
                p = f'rec_{r.pk}_'
                total_subs = Decimal('0')
                subsidios_aplicaveis = []
                for subsidio in subsidios_ativos:
                    if subsidio.apenas_especificos:
                        if subsidio.colaboradores_especificos.filter(id=r.colaborador.id).exists():
                            subsidios_aplicaveis.append(subsidio)
                    else:
                        subsidios_aplicaveis.append(subsidio)

                for subsidio in subsidios_aplicaveis:
                    v = _dec(request.POST.get(f'{p}subsidio_{subsidio.pk}', '0'))
                    vinculo, created = SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=r, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )
                    if not created:
                        vinculo.valor = v
                        vinculo.save()
                    total_subs += v

                SubsidioReciboInstitucional.objects.filter(recibo=r).exclude(
                    subsidio_id__in=[s.pk for s in subsidios_aplicaveis]
                ).delete()
                r.outros_subsidios = total_subs
                r.subsidio_alimentacao = Decimal('0')
                r.subsidio_transporte = Decimal('0')
                faltas_count = int(request.POST.get(f'{p}faltas', '0') or '0')
                r.outros_descontos = (r.salario_base / Decimal('22') * faltas_count).quantize(Decimal('0.01')) if faltas_count > 0 else Decimal('0')
                base_impostos = r.base_calculo_impostos
                r.irt = _calcular_irt(base_impostos)
                r.inss_trabalhador = (base_impostos * Decimal('0.03')).quantize(Decimal('0.01'))
                r.inss_entidade = (base_impostos * Decimal('0.08')).quantize(Decimal('0.01'))
                r.save()
            messages.success(request, 'Alterações guardadas.')

        elif action == 'processar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total líquido é 0,00 KZ. Verifique os dados.')
                return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)
            proc.estado = 'Processado'
            proc.processado_em = timezone.now()
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} processado.')

        elif action == 'pagar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total líquido é 0,00 KZ.')
                return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)
            proc.estado = 'Pago'
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} pago.')

        elif action == 'reabrir':
            if proc.estado == 'Processado':
                proc.estado = 'Rascunho'
                proc.processado_em = None
                proc.save()
                messages.success(request, 'Processamento reaberto.')
            else:
                messages.error(request, 'Apenas processamentos "Processado" podem ser reabertos.')
        return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)

    subsidios_ativos = SubsidioInstitucional.objects.filter(ativo=True)
    tem_faltantes = False
    for r in recibos:
        for subsidio in subsidios_ativos:
            if not subsidio.obrigatorio:
                continue
            if SubsidioReciboInstitucional.objects.filter(recibo=r, subsidio=subsidio).exists():
                continue
            tem_faltantes = True
            if subsidio.tipo_calculo == 'PERCENTUAL':
                v = (r.salario_base * subsidio.percentual) / 100 if subsidio.percentual and r.salario_base else subsidio.valor_padrao
            elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                v = subsidio.valor_padrao * 22
            elif subsidio.tipo_calculo == 'DEPENDENTES':
                v = subsidio.valor_padrao * 1
            else:
                v = subsidio.valor_padrao
            SubsidioReciboInstitucional.objects.get_or_create(
                recibo=r, subsidio=subsidio,
                defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
            )
    if tem_faltantes:
        recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    ctx = _ctx_admin(request, sub='salarios_inst', active_menu='RH_INST', extra={
        'proc': proc, 'recibos': recibos, 'meses': MESES,
        'subsidios_ativos': subsidios_ativos,
    })
    return render(request, 'rh/admin/salario_inst_detalhe.html', ctx)


@_requer_admin_ou_permissoes('processar_salarios_inst')
def admin_salario_inst_apagar_view(request, pk):
    from users.models import ProcessamentoSalarialInstitucional

    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado == 'Pago':
        messages.error(request, 'Processamentos Pago são permanentes.')
        return redirect('rh_admin_salarios_inst')
    if request.method == 'POST':
        label = f'{proc.mes:02d}/{proc.ano}'
        proc.delete()
        messages.success(request, f'Processamento {label} apagado.')
        return redirect('rh_admin_salarios_inst')
    ctx = _ctx_admin(request, sub='salarios_inst', active_menu='RH_INST', extra={'proc': proc})
    return render(request, 'rh/admin/salario_inst_apagar.html', ctx)


@_requer_admin_ou_permissoes('processar_salarios_inst')
def admin_salario_inst_download_view(request, pk):
    from users.models import ProcessamentoSalarialInstitucional
    from django.http import HttpResponse

    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado != 'Pago':
        messages.error(request, 'PDF disponível apenas para processamentos "Pago".')
        return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)
    try:
        from .views_institucional import _gerar_pdf_processamento_inst
        buffer = _gerar_pdf_processamento_inst(proc, request)
        if buffer is None:
            raise RuntimeError("PDF generation returned None")
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="comprovante_pagamento_inst_{proc.mes:02d}_{proc.ano}.pdf"'
        return response
    except Exception as e:
        messages.error(request, f'Erro ao gerar PDF: {str(e)}')
        return redirect('rh_admin_salario_inst_detalhe', pk=proc.pk)


# ══════════════════════════════════════════════════════════════════════════
# BANCA CENTRAL
# ══════════════════════════════════════════════════════════════════════════

from .models import BancaCentral


@_requer_admin
def banca_central_view(request):
    """Dashboard da Banca Central — visão geral da instituição."""
    banca = BancaCentral.get_instance()
    if not banca or not banca.ativa:
        return redirect('rh_banca_central_criar')

    stats_colab = {
        'total': ColaboradorInstitucional.objects.count(),
        'ativos': ColaboradorInstitucional.objects.filter(estado='Ativo').count(),
    }
    stats_bancas = {
        'total': Banca.objects.filter(ativa=True).count(),
        'despachantes': Banca.objects.filter(ativa=True).values('usuario_id').distinct().count(),
    }

    from users.models import VagaInstitucional, CandidaturaInstitucional
    vagas_qs = VagaInstitucional.objects.aggregate(
        vagas_abertas=Count('id', filter=Q(estado='Aberta')),
        total_vagas=Count('id'),
    )
    candidaturas_stats = CandidaturaInstitucional.objects.aggregate(
        total=Count('id'),
        pendentes=Count('id', filter=Q(estado='Recebida')),
        entrevistas=Count('id', filter=Q(estado='Entrevista')),
        aprovados=Count('id', filter=Q(estado='Aprovado')),
    )

    colaboradores_recentes = ColaboradorInstitucional.objects.order_by('-criado_em')[:5]
    candidaturas_recentes = CandidaturaInstitucional.objects.select_related('vaga').order_by('-criado_em')[:5]
    bancas_despachantes = Banca.objects.filter(ativa=True).select_related().order_by('nome')[:10]

    ctx = _ctx_admin(request, sub='banca_central', active_menu='RH_INST', extra={
        'banca': banca,
        'total_colaboradores': stats_colab['total'],
        'colaboradores_activos': stats_colab['ativos'],
        'total_bancas': stats_bancas['total'],
        'total_despachantes': stats_bancas['despachantes'],
        'vagas_abertas': vagas_qs['vagas_abertas'],
        'total_vagas': vagas_qs['total_vagas'],
        'total_candidaturas': candidaturas_stats['total'],
        'candidaturas_pendentes': candidaturas_stats['pendentes'],
        'entrevistas_agendadas': candidaturas_stats['entrevistas'],
        'candidatos_aprovados': candidaturas_stats['aprovados'],
        'colaboradores_recentes': colaboradores_recentes,
        'candidaturas_recentes': candidaturas_recentes,
        'bancas_despachantes': bancas_despachantes,
    })
    return render(request, 'rh/admin/banca_central_dashboard.html', ctx)


@_requer_admin
def banca_central_criar_view(request):
    """Criar a Banca Central (apenas se não existir)."""
    if BancaCentral.objects.filter(ativa=True).exists():
        return redirect('rh_banca_central')

    from rh.views import BANCA_TIPOS, PROVINCIAS

    def _render(extra=None):
        return render(request, 'rh/admin/banca_central_criar.html', _ctx_admin(
            request, sub='banca_central', active_menu='RH_INST',
            extra={'banca_tipos': BANCA_TIPOS, 'provincias': PROVINCIAS, **(extra or {})}))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio']}
        dados['instrucoes_pagamento'] = request.POST.get('instrucoes_pagamento', '').strip()

        bancos_json_raw = request.POST.get('dados_bancarios_json', '[]').strip()
        try:
            bancos_lista = json.loads(bancos_json_raw) if bancos_json_raw else []
        except (json.JSONDecodeError, ValueError):
            bancos_lista = []
        if not isinstance(bancos_lista, list):
            bancos_lista = []
        bancos_lista = [b for b in bancos_lista if isinstance(b, dict) and b.get('banco')]
        if len(bancos_lista) > 4:
            bancos_lista = bancos_lista[:4]

        if not dados['nome'] or not dados['nif']:
            return _render({'erro': 'Nome e NIF são obrigatórios.'})

        if BancaCentral.objects.filter(nif=dados['nif']).exists():
            return _render({'erro': 'Já existe um registo com este NIF.'})

        banca = BancaCentral(**dados)
        banca.dados_bancarios_json = json.dumps(bancos_lista, ensure_ascii=False)
        if bancos_lista:
            banca.banco = bancos_lista[0].get('banco', '')
            banca.iban = bancos_lista[0].get('iban', '')
        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        if 'assinatura' in request.FILES:
            banca.assinatura = request.FILES['assinatura']
        banca.save()

        messages.success(request, 'Banca Central criada com sucesso.')
        return redirect('rh_banca_central')

    return _render()


@_requer_admin
def banca_central_editar_view(request):
    """Editar dados da Banca Central."""
    banca = BancaCentral.get_instance()
    if not banca:
        return redirect('rh_banca_central_criar')

    from rh.views import BANCA_TIPOS, PROVINCIAS

    def _render(extra=None):
        form_data = {
            'nome': banca.nome, 'nif': banca.nif, 'tipo': banca.tipo,
            'email': banca.email, 'telefone': banca.telefone,
            'endereco': banca.endereco, 'provincia': banca.provincia,
            'municipio': banca.municipio,
            'instrucoes_pagamento': banca.instrucoes_pagamento,
            'dados_bancarios_json': banca.dados_bancarios_json or '[]',
        }
        return render(request, 'rh/admin/banca_central_editar.html', _ctx_admin(
            request, sub='banca_central', active_menu='RH_INST',
            extra={'banca': banca, 'banca_tipos': BANCA_TIPOS,
                   'provincias': PROVINCIAS, 'form': form_data, **(extra or {})}))

    if request.method == 'POST':
        dados = {k: request.POST.get(k, '').strip() for k in
                 ['nome', 'nif', 'tipo', 'email', 'telefone',
                  'endereco', 'provincia', 'municipio']}
        dados['instrucoes_pagamento'] = request.POST.get('instrucoes_pagamento', '').strip()

        bancos_json_raw = request.POST.get('dados_bancarios_json', '[]').strip()
        try:
            bancos_lista = json.loads(bancos_json_raw) if bancos_json_raw else []
        except (json.JSONDecodeError, ValueError):
            bancos_lista = []
        if not isinstance(bancos_lista, list):
            bancos_lista = []
        bancos_lista = [b for b in bancos_lista if isinstance(b, dict) and b.get('banco')]
        if len(bancos_lista) > 4:
            bancos_lista = bancos_lista[:4]

        if not dados['nome'] or not dados['nif']:
            return _render({'erro': 'Nome e NIF são obrigatórios.'})

        if BancaCentral.objects.filter(nif=dados['nif']).exclude(pk=banca.pk).exists():
            return _render({'erro': 'Já existe outro registo com este NIF.'})

        for k, v in dados.items():
            setattr(banca, k, v)

        banca.dados_bancarios_json = json.dumps(bancos_lista, ensure_ascii=False)
        if bancos_lista:
            banca.banco = bancos_lista[0].get('banco', '')
            banca.iban = bancos_lista[0].get('iban', '')
        else:
            banca.banco = ''
            banca.iban = ''

        if 'logo' in request.FILES:
            banca.logo = request.FILES['logo']
        if 'assinatura' in request.FILES:
            banca.assinatura = request.FILES['assinatura']
        banca.save()

        messages.success(request, 'Dados da Banca Central actualizados com sucesso.')
        return redirect('rh_banca_central')

    return _render()


@_requer_admin
def banca_central_detalhe_view(request):
    """Informações detalhadas da Banca Central."""
    banca = BancaCentral.get_instance()
    if not banca:
        return redirect('rh_banca_central_criar')

    ctx = _ctx_admin(request, sub='banca_central', active_menu='RH_INST', extra={'banca': banca})
    return render(request, 'rh/admin/banca_central_info.html', ctx)
