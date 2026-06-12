from .models import Usuario, Permissao


def _is_admin_ou_acesso_total(request):
    """True se papel=Administrador ou tiver permissão 'admin' (direta ou via função)."""
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
    # Verificar se a função do colaborador tem a permissão 'admin'
    return Usuario.objects.filter(
        pk=usuario_id, papel='Colaborador Institucional', funcao__permissoes__codigo='admin'
    ).exists()


def _get_usuario_funcao_permissoes(usuario):
    """Retorna set de códigos de permissão vindos da função do usuário."""
    if not usuario or not usuario.funcao_id:
        return set()
    return set(usuario.funcao.permissoes.values_list('codigo', flat=True))


def get_usuario_permissoes(request):
    """Retorna set de códigos de permissão do usuário logado (diretas + função)."""
    if not request.session.get('usuario_id'):
        return set()
    if _is_admin_ou_acesso_total(request):
        return set(Permissao.objects.values_list('codigo', flat=True))
    usuario_id = request.session['usuario_id']
    usuario = Usuario.objects.filter(pk=usuario_id).select_related('funcao').prefetch_related(
        'permissoes_diretas'
    ).first()
    if not usuario:
        return set()
    permissoes = set(usuario.permissoes_diretas.values_list('codigo', flat=True))
    # Adicionar permissões da função (apenas para Colaborador Institucional)
    if usuario.papel == 'Colaborador Institucional':
        permissoes.update(_get_usuario_funcao_permissoes(usuario))
    # Se o usuário tem acesso_auditoria, expande para todos os códigos ver_*
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
    usuario_id = request.session['usuario_id']
    if codigo.startswith('ver_'):
        if Usuario.objects.filter(pk=usuario_id, permissoes_diretas__codigo='acesso_auditoria').exists():
            return True
    # Verificar permissão direta ou via função
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
