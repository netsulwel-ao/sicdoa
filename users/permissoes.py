from .models import Usuario, Permissao


def _get_all_permissoes(usuario):
    """Retorna set de códigos de permissão de um usuario (cargos + diretas)."""
    permissoes = set()
    for cargo in usuario.cargos.all():
        for p in cargo.permissoes.all():
            permissoes.add(p.codigo)
    for p in usuario.permissoes_diretas.all():
        permissoes.add(p.codigo)
    return permissoes


def get_usuario_permissoes(request):
    """Retorna set de códigos de permissão do usuário logado."""
    if not request.session.get('usuario_id'):
        return set()
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return set(Permissao.objects.values_list('codigo', flat=True))
    usuario_id = request.session['usuario_id']
    usuario = Usuario.objects.filter(pk=usuario_id).only('id').prefetch_related(
        'cargos__permissoes', 'permissoes_diretas'
    ).first()
    if not usuario:
        return set()
    return _get_all_permissoes(usuario)


def usuario_tem_permissao(request, codigo):
    """Verifica se o usuário logado tem uma permissão específica."""
    if not request.session.get('usuario_id'):
        return False
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return True
    usuario_id = request.session['usuario_id']
    usuario = Usuario.objects.filter(pk=usuario_id).only('id').prefetch_related(
        'cargos__permissoes', 'permissoes_diretas'
    ).first()
    if not usuario:
        return False
    return any(
        cargo.permissoes.filter(codigo=codigo).exists()
        for cargo in usuario.cargos.all()
    ) or usuario.permissoes_diretas.filter(codigo=codigo).exists()


def usuario_obj_tem_permissao(usuario, codigo):
    """Verifica se um objecto Usuario tem uma permissão específica."""
    if not usuario:
        return False
    if usuario.papel == 'Administrador':
        return True
    usuario_db = Usuario.objects.filter(pk=usuario.pk).only('id').prefetch_related(
        'cargos__permissoes', 'permissoes_diretas'
    ).first()
    if not usuario_db:
        return False
    return any(
        cargo.permissoes.filter(codigo=codigo).exists()
        for cargo in usuario_db.cargos.all()
    ) or usuario_db.permissoes_diretas.filter(codigo=codigo).exists()
