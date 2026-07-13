"""
Controlo de acesso RH — Matriz de aprovação profissional.

=====================================================================
 FLUXO DE APROVAÇÃO — PRESENÇAS E FÉRIAS
=====================================================================

 CONTEXTO
 --------
 O sistema segue uma hierarquia de aprovação com 3 níveis:
   1. RH Filial   — colaborador com permissão "gerir_rh" E filial atribuída
   2. RH Sede     — colaborador com permissão "gerir_rh" SEM filial (sede)
   3. Despachante — utilizador dono da banca (não é Colaborador)

 MATRIZ DE APROVAÇÃO (pode_aprovar_presenca)
 --------------------------------------------
 ┌──────────────────┬──────────┬────────┬──────────┬──────────┐
 │ Aprovador \ Alvo │ Reg Sede │ Reg Fi │ RH Fi    │ RH Se    │
 ├──────────────────┼──────────┼────────┼──────────┼──────────┤
 │ RH Filial (mf)   │    ❌    │   ✅   │    ❌    │   ❌     │
 │ RH Sede          │    ✅    │   ✅   │    ✅    │   ❌     │
 │ Despachante (*)  │    ⚠️    │   ⚠️   │    ⚠️    │   ✅     │
 └──────────────────┴──────────┴────────┴──────────┴──────────┘
 (*) Despachante aprova RH Sede sempre;
     restantes apenas como fallback quando NÃO existe colaborador
     RH ao nível necessário.

 REGRAS GERAIS
 -------------
 • Auto-aprovação: sempre proibida.
   - RH Filial NÃO aprova a si próprio nem a outro RH da mesma filial.
   - RH Sede NÃO aprova a si próprio nem a outro RH Sede.
 • Delegação: se o aprovador tem delegação ativa do alvo
   (DelegacaoAprovacao), a aprovação é permitida como fallback.
 • Despachante: a matriz original permitia-lhe aprovar QUALQUER
   registo. Foi restringido para só aprovar directamente o RH Sede;
   para os demais níveis, só aprova quando não existe colaborador RH
   disponível (fallback).

 NOTIFICAÇÕES (_encontrar_responsavel_aprovacao)
 ------------------------------------------------
 Quando um colaborador cria um registo (presença ou férias), o sistema
 encontra o responsável pela aprovação e notifica-o:

 ┌──────────────────┬──────────────────────────────────────────────┐
 │ Alvo             │ Responsável notificado                       │
 ├──────────────────┼──────────────────────────────────────────────┤
 │ RH Sede          │ Ninguém (visto manualmente pelo Despachante) │
 │ RH Filial        │ RH Sede                                      │
 │ Regular Sede     │ RH Sede                                      │
 │ Regular Filial   │ RH Filial (mesma filial) → RH Sede (fallback)│
 └──────────────────┴──────────────────────────────────────────────┘

 • Quando o responsável não é encontrado (None), o registo fica
   pendente para o Despachante verificar manualmente. NÃO é enviado
   email — decisão do cliente (2026-06-24).
 • As notificações são in-app (NotificacaoRH) + email.

 HISTÓRICO (HistoricoPresenca)
 ------------------------------
 Todas as acções geram registo de auditoria:
   CRIADA, ALTERADA, APROVADA, REJEITADA, REMOVIDA, FALTA_AUTO
 • O aprovador é opcional (null) — quando o Despachante aprova,
   fica NULL pois não tem Colaborador associado.

 VALIDAÇÃO DE FÉRIAS (PedidoFerias.clean)
 -----------------------------------------
 • Não permite criar pedidos com data no passado.
 • Valida que data_fim >= data_inicio.
 • Valida que NÃO exista outro pedido APROVADO com período
   sobreposto para o mesmo colaborador.

 MARCAÇÃO AUTOMÁTICA DE FALTAS (auto_marcar_faltas)
 ---------------------------------------------------
 O comando `python manage.py auto_marcar_faltas` percorre todos os
 colaboradores activos e cria RegistoPresenca com tipo='Falta' para
 dias úteis sem registo. Gera HistoricoPresenca (FALTA_AUTO) e
 notifica o responsável pela aprovação.

 INTEGRAÇÃO FÉRIAS → PRESENÇAS (marcar_ferias_no_registo)
 ---------------------------------------------------------
 Quando férias são aprovadas, os dias úteis do período são marcados
 como 'Ferias' nos registos de presença. Apenas sobrescreve registos
 do tipo 'Falta' ou 'Falta_Justificada'; preserva presenças reais
 ('Entrada', 'Hora_Extra') já existentes.

=====================================================================
 ALTERAÇÕES REALIZADAS (2026-06-24)
=====================================================================
 1. Restrição do Despachante:
    - Antes: aprovava qualquer registo indiscriminadamente.
    - Agora: aprovado conforme matriz acima, com fallback apenas
      quando não existe RH ao nível necessário.
 2. Notificação do Despachante por email:
    - Implementada e removida a pedido do cliente ("deve ser visto
      de forma manual").
 3. auto_marcar_faltas:
    - Antes: criava RegistoPresenca sem histórico nem notificação.
    - Agora: gera HistoricoPresenca (FALTA_AUTO) + notifica
      responsável.
 4. Sobreposição de férias:
    - Antes: não validava.
    - Agora: rejeita pedidos com período sobreposto a férias já
      aprovadas.
 5. marcar_ferias_no_registo:
    - Antes: sobrescrevia qualquer registo de presença (inclusive
      Entrada/Hora_Extra).
    - Agora: só sobrescreve Falta/Falta_Justificada; preserva
      presenças reais.
=====================================================================
"""
from django.db import models
from django.shortcuts import redirect
from django.utils import timezone

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
    Colaboradores com permissão gerir_rh ou que são gestores de filial
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
            'gerir_rh', 'gerir_filial',
            'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
            'gerir_processamento_salarial', 'gerir_recrutamento_banca',
            'gerir_presencas_banca', 'gerir_avaliacoes_banca',
        ]
        tem_perm_rh = (col.e_gestor_filial
                       or any(p in permissoes for p in perms_rh_granular))
        if not tem_perm_rh:
            return None
        try:
            gestor_filial = col.gestor_filial
        except Colaborador.gestor_filial.RelatedObjectDoesNotExist:
            gestor_filial = None
        return col.banca, col, gestor_filial, False

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
    - Utilizador na Sede com permissão RH granular/gestão: toda a banca
    - Gestor de filial (sem permissão RH): apenas a filial que gere + o próprio
    - Colaborador com filial: apenas a própria filial + o próprio
    - Demais colaboradores: apenas o próprio
    """
    qs = banca.colaboradores.all()
    if is_despachante:
        return qs
    # Utilizador na Sede com permissão RH vê toda a banca
    if request and col_logado and not col_logado.filial_id:
        permissoes = get_usuario_permissoes(request)
        if any(p in permissoes for p in (
            'gerir_rh', 'gerir_filial', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
            'gerir_processamento_salarial', 'gerir_recrutamento_banca',
            'gerir_presencas_banca', 'gerir_avaliacoes_banca',
            'admin_banca',
        )):
            return qs
    # Gestor: âmbito é a filial que gere (pode ser diferente da sua filial de trabalho)
    if gestor and gestor.filial_id:
        return qs.filter(models.Q(filial_id=gestor.filial_id) | models.Q(pk=col_logado.pk))
    # Colaborador com filial: âmbito é apenas a própria filial
    if col_logado and col_logado.filial_id:
        return qs.filter(models.Q(filial_id=col_logado.filial_id) | models.Q(pk=col_logado.pk))
    # Fallback: utilizador na Sede sem permissão RH vê apenas o próprio
    return qs.filter(pk=col_logado.pk)


def escopo_colaboradores_ativos(banca, col_logado, gestor, is_despachante, request=None):
    return escopo_colaboradores(banca, col_logado, gestor, is_despachante, request).filter(
        estado='Ativo',
    )


def escopo_vagas(banca, col_logado, gestor, is_despachante, request=None):
    if is_despachante:
        return banca.vagas.all()
    # Gestor: vagas da filial que gere
    if gestor and gestor.filial_id:
        return banca.vagas.filter(filial_id=gestor.filial_id)
    # Colaborador com filial: vagas da própria filial
    if col_logado and col_logado.filial_id:
        return banca.vagas.filter(filial_id=col_logado.filial_id)
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
    if gestor and gestor.filial_id:
        return colaborador.filial_id == gestor.filial_id
    if col_logado and col_logado.filial_id:
        return colaborador.filial_id == col_logado.filial_id
    return True


def pode_aceder_vaga(gestor, is_despachante, vaga):
    if vaga is None:
        return False
    if vaga.estado not in ('Aberta', 'Em Análise'):
        return False
    if is_despachante:
        return True
    if gestor:
        return vaga.filial_id == gestor.filial_id
    return True


def pode_avaliar_colaborador(col_logado, is_despachante, alvo):
    """Gestor não pode auto-avaliar-se; despachante avalia todos."""
    if is_despachante:
        return True
    if col_logado and alvo.pk == col_logado.pk:
        return False
    return True


def _get_colaborador_permissoes(colaborador):
    """Retorna set de permissões de um colaborador via cargo_banca."""
    if not colaborador or not colaborador.cargo_banca_id:
        return set()
    return set(colaborador.cargo_banca.permissoes.values_list('codigo', flat=True))


def _existe_aprovador_rh(banca, filial_id=None):
    """QuerySet de colaboradores com permissão de aprovação."""
    return banca.colaboradores.filter(
        estado='Ativo', filial_id=filial_id,
    ).filter(
        models.Q(cargo_banca__permissoes__codigo='gerir_rh') |
        models.Q(cargo_banca__permissoes__codigo='gerir_filial') |
        models.Q(cargo_banca__permissoes__codigo='gerir_presencas_banca'),
    )


def _colaborador_eh_rh_sede(colaborador, perm_set=None):
    """True se o colaborador é RH ao nível da Sede (gerir_rh, sem filial_id)."""
    if not colaborador or colaborador.filial_id:
        return False
    if perm_set is None:
        perm_set = _get_colaborador_permissoes(colaborador)
    return 'gerir_rh' in perm_set


def _colaborador_eh_rh_filial(colaborador, perm_set=None):
    """True se o colaborador é RH de uma filial (gerir_rh + filial_id)."""
    if not colaborador or not colaborador.filial_id:
        return False
    if perm_set is None:
        perm_set = _get_colaborador_permissoes(colaborador)
    return 'gerir_rh' in perm_set


def _delegacao_ativa_para(banca, delegante, aprovador):
    """Verifica se aprovador tem delegação ativa do delegante."""
    hoje = timezone.now().date()
    return DelegacaoAprovacao.objects.filter(
        banca=banca, delegante=delegante, delegado=aprovador,
        ativo=True, data_inicio__lte=hoje, data_fim__gte=hoje,
    ).exists()


def _colaborador_eh_gestor_filial(colaborador, filial_id_alvo=None):
    """
    True se o colaborador é Gestor de Filial (Responsável).
    Se filial_id_alvo for fornecido, verifica se gere essa filial específica.
    """
    if not colaborador or not colaborador.e_gestor_filial:
        return False
    if filial_id_alvo is not None:
        return colaborador.gestor_filial.filial_id == filial_id_alvo
    return True


def pode_aprovar_presenca(request, banca, aprovador_col, is_desp, target_col):
    """
    Matriz de aprovação profissional para presenças e férias.

    Níveis:
    ┌─────────────────────┬──────────┬────────┬──────────┬──────────┐
    │ Aprovador \ Alvo    │ Reg Sede │ Reg Fi │ RH Fi    │ RH Se    │
    ├─────────────────────┼──────────┼────────┼──────────┼──────────┤
    │ Gestor Filial (mf)  │    ❌    │   ✅   │    ❌    │   ❌     │
    │ RH Filial (mf)      │    ❌    │   ✅   │    ❌    │   ❌     │
    │ RH Sede             │    ✅    │   ✅   │    ✅    │   ❌     │
    │ Despachante (*)     │    ⚠️    │   ⚠️   │    ⚠️    │   ✅     │
    └─────────────────────┴──────────┴────────┴──────────┴──────────┘
    (*) Despachante aprova RH Sede sempre; restantes apenas como fallback
        quando não há colaborador RH ao nível necessário.

    - RH* = colaborador com gerir_rh ou gerir_presencas_banca
    - Auto-aprovação: sempre ❌
    - Fallback: se não houver RH ao nível necessário, sobe ao nível superior
    - Delegação: se aprovador tem delegação ativa do alvo, permite
    - Gestor de Filial (Responsável): aprova apenas colaboradores regulares
      da filial que gere.
    """
    from .models import DelegacaoAprovacao

    # 0 — Auto-aprovação proibida
    if aprovador_col and target_col and aprovador_col.pk == target_col.pk:
        return False

    if not target_col:
        return False

    # 1 — Permissões do alvo (necessárias antes do bloco do Despachante)
    perm_target = _get_colaborador_permissoes(target_col)
    target_is_sede_rh = _colaborador_eh_rh_sede(target_col, perm_target)
    target_is_filial_rh = _colaborador_eh_rh_filial(target_col, perm_target)

    # 2 — Despachante: aprova todos da sua banca
    if is_desp:
        return True

    if not aprovador_col:
        return False

    # 3 — Permissões do aprovador
    perm_aprovador = get_usuario_permissoes(request)
    is_filial_rh = _colaborador_eh_rh_filial(aprovador_col, perm_aprovador)
    is_sede_rh = _colaborador_eh_rh_sede(aprovador_col, perm_aprovador)

    # Utilizadores com gerir_filial / gerir_presencas_banca (sem gerir_rh)
    # têm os mesmos poderes de aprovação, respeitando o âmbito (filial vs sede)
    _perm_aprovar_set = {'gerir_filial', 'gerir_presencas_banca'}
    if not is_filial_rh and not is_sede_rh and _perm_aprovar_set & perm_aprovador:
        if aprovador_col.filial_id:
            is_filial_rh = True
        else:
            is_sede_rh = True

    # 4 — Regras da matriz (aprovadores não-despachante)
    # 4a — Alvo é RH Sede → só Despachante
    if target_is_sede_rh:
        return False

    # 4b — Alvo é RH Filial → Sede RH ou Gestor da mesma filial
    if target_is_filial_rh:
        if is_sede_rh:
            return True
        if is_filial_rh and aprovador_col.filial_id == target_col.filial_id:
            return False  # mesma filial → auto-aprovação indirecta proibida
        # Gestor de Filial pode aprovar RH Filial da filial que gere
        if _colaborador_eh_gestor_filial(aprovador_col, target_col.filial_id):
            return True
        return False

    # 4c — Alvo é regular Sede → Sede RH
    if not target_col.filial_id:
        if is_sede_rh:
            return True
        if is_filial_rh:
            return False  # RH Filial não aprova Sede
        return False

    # 4d — Alvo é regular Filial → RH Filial ou Gestor da mesma filial, ou Sede RH
    if is_sede_rh:
        return True
    if is_filial_rh and aprovador_col.filial_id == target_col.filial_id:
        return True
    # Gestor de Filial (Responsável) aprova colaboradores da filial que gere
    if _colaborador_eh_gestor_filial(aprovador_col, target_col.filial_id):
        return True

    # 5 — Verificar delegação activa
    if _delegacao_ativa_para(banca, target_col, aprovador_col):
        return True

    return False


def filial_id_obrigatoria_gestor(gestor, is_despachante, filial_id_post, col_log=None, banca=None):
    """Em criações, gestor só pode associar à sua filial.
    RH Filial (não gestor) fica escopo à sua própria filial.
    Despachante: valida que filial pertence à banca."""
    if is_despachante:
        if filial_id_post and banca:
            if not banca.filiais.filter(pk=filial_id_post, ativa=True).exists():
                return None
        return filial_id_post or None
    if gestor:
        return gestor.filial_id
    if col_log and col_log.filial_id:
        return col_log.filial_id
    return filial_id_post or None


def contexto_colaborador(request):
    """
    Retorna um dict com variáveis de contexto do colaborador logado
    para uso nas sidebars: colaborador_logado, e_gestor_filial,
    filial_gestor, user_permissoes, e_responsavel.

    Se o user não for colaborador, retorna dict vazio.
    """
    from users.permissoes import get_usuario_permissoes
    if request.session.get('tipo_usuario') != 'colaborador':
        return {}
    cid = request.session.get('colaborador_id')
    if not cid:
        return {}
    try:
        col = Colaborador.objects.select_related(
            'banca', 'filial', 'gestor_filial__filial',
        ).get(pk=cid, estado='Ativo')
    except Colaborador.DoesNotExist:
        return {}
    permissoes = get_usuario_permissoes(request)
    e_gestor = col.e_gestor_filial
    try:
        filial_gestor = col.gestor_filial.filial if e_gestor else None
    except Exception:
        filial_gestor = None
    return {
        'colaborador': col,
        'colaborador_logado': col,
        'e_gestor_filial': e_gestor,
        'e_responsavel': e_gestor or ('gerir_rh' in permissoes and not col.filial_id),
        'filial_gestor': filial_gestor,
        'user_permissoes': permissoes,
    }


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
