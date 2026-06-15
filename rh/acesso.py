"""
Controlo de acesso RH: despachante (acesso total) vs gestor de filial (âmbito da filial).
Administrador do sistema pode gerir todos os despachantes e bancas.
"""
from django.db import models
from django.shortcuts import redirect

from .models import Banca, Colaborador
from users.permissoes import (
    _is_admin_ou_acesso_total,
    get_usuario_permissoes,
)


def obter_acesso_admin(request):
    """
    Retorna True se o utilizador em sessão é Administrador do sistema.
    Administradores podem gerir todos os despachantes e bancas.
    """
    uid = request.session.get('usuario_id')
    if not uid:
        return False
    papel = request.session.get('usuario', {}).get('papel', '')
    return _is_admin_ou_acesso_total(request)


def obter_acesso_rh(request):
    """
    Retorna (banca, colaborador_logado, gestor_filial, is_despachante) ou None.
    Colaboradores com permissão gerir_rh/gerir_rh_filial ou que são gestores de filial
    podem aceder ao módulo RH.
    Despachantes e Administradores acedem via sessão de utilizador.
    """
    if request.session.get('tipo_usuario') == 'colaborador':
        cid = request.session.get('colaborador_id')
        if not cid:
            return None
        try:
            col = Colaborador.objects.select_related(
                'banca', 'filial', 'gestor_filial__filial',
            ).get(pk=cid, estado='Ativo')
        except Colaborador.DoesNotExist:
            return None
        # Verificar permissões: gestor de filial clássico OU permissões RH (grossas ou granulares)
        permissoes = get_usuario_permissoes(request)
        perms_rh_granular = [
            'gerir_rh', 'gerir_rh_filial', 'gerir_filial',
            'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
            'gerir_processamento_salarial', 'gerir_recrutamento_banca',
            'gerir_presencas_banca', 'gerir_avaliacoes_banca',
        ]
        tem_perm_rh = (col.e_gestor_filial
                       or any(p in permissoes for p in perms_rh_granular))
        if not tem_perm_rh:
            return None
        return col.banca, col, col.gestor_filial, False

    uid = request.session.get('usuario_id')
    if uid:
        banca = Banca.objects.filter(usuario_id=uid, ativa=True).first()
        if banca:
            return banca, None, None, True
    return None


def escopo_colaboradores(banca, col_logado, gestor, is_despachante, request=None):
    """
    Colaboradores visíveis:
    - Despachante: toda a banca
    - Colaborador com gerir_rh ou qualquer permissão RH granular de gestão: toda a banca
    - Colaborador com gerir_rh_filial ou gestor_clássico: apenas a filial + o próprio
    """
    qs = banca.colaboradores.all()
    if is_despachante:
        return qs
    if request:
        permissoes = get_usuario_permissoes(request)
        if any(p in permissoes for p in (
            'gerir_rh', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
            'gerir_processamento_salarial', 'gerir_recrutamento_banca',
            'gerir_presencas_banca', 'gerir_avaliacoes_banca',
            'admin_banca',
        )):
            return qs
    if not gestor or not gestor.filial_id:
        return qs.filter(pk=col_logado.pk)
    return qs.filter(models.Q(filial_id=gestor.filial_id) | models.Q(pk=col_logado.pk))


def escopo_colaboradores_ativos(banca, col_logado, gestor, is_despachante, request=None):
    return escopo_colaboradores(banca, col_logado, gestor, is_despachante, request).filter(
        estado='Ativo',
    )


def escopo_vagas(banca, gestor, is_despachante, request=None):
    if is_despachante:
        return banca.vagas.all()
    if request:
        permissoes = get_usuario_permissoes(request)
        if any(p in permissoes for p in (
            'gerir_rh', 'gerir_recrutamento_banca', 'admin_banca',
        )):
            return banca.vagas.all()
    if not gestor or not gestor.filial_id:
        return banca.vagas.none()
    return banca.vagas.filter(filial_id=gestor.filial_id)


def pode_aceder_colaborador(banca, col_logado, gestor, is_despachante, colaborador):
    if colaborador.banca_id != banca.pk:
        return False
    if is_despachante:
        return True
    if colaborador.pk == col_logado.pk:
        return True
    if not gestor or not gestor.filial_id:
        return True
    return colaborador.filial_id == gestor.filial_id


def pode_aceder_vaga(gestor, is_despachante, vaga):
    if is_despachante:
        return True
    return vaga.filial_id == gestor.filial_id


def pode_avaliar_colaborador(col_logado, is_despachante, alvo):
    """Gestor não pode auto-avaliar-se; despachante avalia todos."""
    if is_despachante:
        return True
    if col_logado and alvo.pk == col_logado.pk:
        return False
    return True


def filial_id_obrigatoria_gestor(gestor, is_despachante, filial_id_post):
    """Em criações, gestor só pode associar à sua filial."""
    if is_despachante:
        return filial_id_post or None
    return gestor.filial_id


def redirect_sem_acesso_rh(request):
    if request.session.get('tipo_usuario') == 'colaborador':
        return redirect('dashboard_colaborador')
    papel = request.session.get('usuario', {}).get('papel', '')
    if _is_admin_ou_acesso_total(request):
        return redirect('dashboard')
    if Banca.objects.filter(
        usuario_id=request.session.get('usuario_id'), ativa=True,
    ).exists():
        return redirect('rh_banca')
    return redirect('rh_banca_criar')


# ─── Acesso RH Institucional ─────────────────────────────────────────────

INST_PERMISSOES_MAP = {
    'dashboard':        ['gerir_colaboradores_inst', 'gerir_presencas_inst', 'gerir_ferias_inst',
                         'gerir_avaliacoes_inst', 'processar_salarios_inst',
                         'gerir_recrutamento_inst', 'gerir_subsidios_inst'],
    'colaboradores':    ['gerir_colaboradores_inst'],
    'presencas':        ['gerir_presencas_inst', 'gerir_ferias_inst'],
    'avaliacoes':       ['gerir_avaliacoes_inst'],
    'salarios':         ['processar_salarios_inst', 'gerir_subsidios_inst'],
    'recrutamento':     ['gerir_recrutamento_inst'],
    'subsidios':        ['gerir_subsidios_inst'],
}


def obter_acesso_inst(request):
    """
    Retorna True se o utilizador tem acesso ao RH Institucional (Admin ou permissão específica).
    """
    if _is_admin_ou_acesso_total(request):
        return True
    permissoes = get_usuario_permissoes(request)
    for perms in INST_PERMISSOES_MAP.values():
        for p in perms:
            if p in permissoes:
                return True
    return False


def obter_acesso_inst_modulo(request, modulo):
    """
    Verifica acesso a um módulo específico do RH Institucional.
    """
    if _is_admin_ou_acesso_total(request):
        return True
    permissoes = get_usuario_permissoes(request)
    perms_necessarias = INST_PERMISSOES_MAP.get(modulo, [])
    for p in perms_necessarias:
        if p in permissoes:
            return True
    return False
