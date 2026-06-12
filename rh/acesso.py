"""
Controlo de acesso RH: despachante (acesso total) vs gestor de filial (âmbito da filial).
Administrador do sistema pode gerir todos os despachantes e bancas.
"""
from django.db import models
from django.shortcuts import redirect

from .models import Banca, Colaborador


def obter_acesso_admin(request):
    """
    Retorna True se o utilizador em sessão é Administrador do sistema.
    Administradores podem gerir todos os despachantes e bancas.
    """
    uid = request.session.get('usuario_id')
    if not uid:
        return False
    papel = request.session.get('usuario', {}).get('papel', '')
    from users.permissoes import _is_admin_ou_acesso_total
    return _is_admin_ou_acesso_total(request)


def obter_acesso_rh(request):
    """
    Retorna (banca, colaborador_logado, gestor_filial, is_despachante) ou None.
    Gestores de filial acedem via sessão de colaborador.
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
        if not col.e_gestor_filial:
            return None
        return col.banca, col, col.gestor_filial, False

    uid = request.session.get('usuario_id')
    if uid:
        banca = Banca.objects.filter(usuario_id=uid, ativa=True).first()
        if banca:
            return banca, None, None, True
    return None


def escopo_colaboradores(banca, col_logado, gestor, is_despachante):
    """Colaboradores visíveis: toda a banca (despachante) ou filial + o próprio gestor."""
    qs = banca.colaboradores.all()
    if is_despachante:
        return qs
    filial = gestor.filial
    return qs.filter(models.Q(filial=filial) | models.Q(pk=col_logado.pk))


def escopo_colaboradores_ativos(banca, col_logado, gestor, is_despachante):
    return escopo_colaboradores(banca, col_logado, gestor, is_despachante).filter(
        estado='Ativo',
    )


def escopo_vagas(banca, gestor, is_despachante):
    if is_despachante:
        return banca.vagas.all()
    return banca.vagas.filter(filial=gestor.filial)


def pode_aceder_colaborador(banca, col_logado, gestor, is_despachante, colaborador):
    if colaborador.banca_id != banca.pk:
        return False
    if is_despachante:
        return True
    if colaborador.pk == col_logado.pk:
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
    from users.permissoes import _is_admin_ou_acesso_total
    if _is_admin_ou_acesso_total(request):
        return redirect('dashboard')
    if Banca.objects.filter(
        usuario_id=request.session.get('usuario_id'), ativa=True,
    ).exists():
        return redirect('rh_banca')
    return redirect('rh_banca_criar')
