from django.db.models import prefetch_related_objects

from .models import Usuario, Permissao

# Permissões exclusivas do sistema institucional (nunca atribuíveis via cargo da banca)
PERMISSOES_INSTITUCIONAIS = [
    'gerir_colaboradores_inst', 'gerir_presencas_inst', 'gerir_ferias_inst',
    'gerir_avaliacoes_inst', 'processar_salarios_inst', 'gerir_recrutamento_inst',
    'gerir_subsidios_inst', 'gerir_utilizadores', 'admin',
    'ver_dashboard', 'acesso_auditoria',
    'ser_membro_mesa', 'aprovar_requisicao', 'ver_rh',
]

# Permissões exclusivas da Banca (só o Despachante concede via cargo)
PERMISSOES_BANCA = [
    # Gestão Aduaneira
    'gerir_aduaneiro', 'criar_declaracao_unica', 'ver_pauta_aduaneira',
    'gerir_clientes', 'gerir_clientes_filial',
    # Filial
    'gerir_filial',
    # RH
    'gerir_rh',
    'ver_minha_banca', 'gerir_colaboradores_banca', 'gerir_cargos_banca',
    'gerir_processamento_salarial', 'gerir_recrutamento_banca',
    'gerir_presencas_banca', 'gerir_avaliacoes_banca',
    # Financeiro
    'gerir_financeiro', 'gerir_financeiro_filial',
    'ver_requisicoes', 'ver_recibos', 'ver_notas_financeiro',
    'ver_facturas', 'ver_conta_corrente', 'ver_relatorios_financeiros',
    # Colaborador
    'alterar_perfil',
    # Administração
    'ver_logs_banca',
    # Super
    'admin_banca',
]

PERMISSOES_AUTO_DESPACHANTE = ['alterar_perfil']


def _is_admin_ou_acesso_total(request):
    """True se papel=Administrador ou tiver permissão 'admin' (direta, via função, ou via cargo_banca)."""
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return True
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return False
    if Usuario.objects.filter(
        pk=usuario_id, permissoes_diretas__codigo='admin'
    ).exists():
        return True
    if Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo='admin'
    ).exists():
        return True
    # Colaborador da Banca: verificar cargo_banca (admin_banca não concede acesso total ao sistema)
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            from rh.models import Colaborador
            if Colaborador.objects.filter(
                pk=colaborador_id, estado='Ativo', cargo_banca__permissoes__codigo='admin'
            ).exists():
                return True
    return False


def _get_usuario_funcao_permissoes(usuario):
    """Retorna set de códigos de permissão vindos da função do usuário."""
    if not usuario or not usuario.funcao_id:
        return set()
    return set(usuario.funcao.permissoes.values_list('codigo', flat=True))


def get_usuario_permissoes(request):
    """Retorna set de códigos de permissão do usuário logado (diretas + função + cargo banca)."""
    if not request.session.get('usuario_id'):
        return set()
    if _is_admin_ou_acesso_total(request):
        return set(Permissao.objects.values_list('codigo', flat=True))
    # Colaboradores: as permissões vêm do cargo_banca (consulta à BD em tempo real)
    if request.session.get('tipo_usuario') == 'colaborador':
        colaborador_id = request.session.get('colaborador_id')
        if colaborador_id:
            from rh.models import Colaborador
            try:
                col = Colaborador.objects.select_related('cargo_banca').prefetch_related(
                    'cargo_banca__permissoes'
                ).get(pk=colaborador_id, estado='Ativo')
                if col.cargo_banca_id:
                    permissoes = set(col.cargo_banca.permissoes.values_list('codigo', flat=True))
                    if 'admin' in permissoes:
                        return set(Permissao.objects.values_list('codigo', flat=True))
                    if 'admin_banca' in permissoes:
                        return set(Permissao.objects.filter(
                            codigo__in=PERMISSOES_BANCA
                        ).values_list('codigo', flat=True))
                    if 'acesso_auditoria' in permissoes:
                        ver_codigos = set(Permissao.objects.filter(codigo__startswith='ver_').values_list('codigo', flat=True))
                        permissoes.update(ver_codigos)
                    return permissoes
            except Colaborador.DoesNotExist:
                pass
        return set()
    usuario_id = request.session['usuario_id']
    usuario = Usuario.objects.filter(pk=usuario_id).select_related('funcao').prefetch_related(
        'permissoes_diretas'
    ).first()
    if not usuario:
        return set()
    permissoes = set(usuario.permissoes_diretas.values_list('codigo', flat=True))
    if usuario.papel == 'Despachante Oficial':
        permissoes.update(PERMISSOES_AUTO_DESPACHANTE)
    if usuario.papel == 'Colaborador Institucional':
        permissoes.update(_get_usuario_funcao_permissoes(usuario))
    if 'acesso_auditoria' in permissoes:
        ver_codigos = set(Permissao.objects.filter(codigo__startswith='ver_').values_list('codigo', flat=True))
        permissoes.update(ver_codigos)
    return permissoes


def usuario_tem_permissao(request, codigo):
    """Verifica se o usuário logado tem uma permissão específica."""
    if not request.session.get('usuario_id'):
        return False
    if _is_admin_ou_acesso_total(request):
        return True
    # Colaborador: verificar permissões do cargo_banca na BD em tempo real
    if request.session.get('tipo_usuario') == 'colaborador':
        return codigo in get_usuario_permissoes(request)
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Despachante Oficial' and codigo in PERMISSOES_AUTO_DESPACHANTE:
        return True
    usuario_id = request.session['usuario_id']
    if codigo.startswith('ver_'):
        if Usuario.objects.filter(pk=usuario_id, permissoes_diretas__codigo='acesso_auditoria').exists():
            return True
    return Usuario.objects.filter(
        pk=usuario_id, permissoes_diretas__codigo=codigo
    ).exists() or Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo=codigo
    ).exists()


def usuario_obj_tem_permissao(usuario, codigo):
    """Verifica se um objecto Usuario tem uma permissão específica."""
    if not usuario:
        return False
    if usuario.papel == 'Administrador':
        return True
    if usuario.permissoes_diretas.filter(codigo='admin').exists():
        return True
    if usuario.papel == 'Colaborador Institucional':
        if usuario.funcao and usuario.funcao.permissoes.filter(codigo=codigo).exists():
            return True
    return Usuario.objects.filter(
        pk=usuario.pk, permissoes_diretas__codigo=codigo
    ).exists()
