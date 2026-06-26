from .permissoes import get_usuario_permissoes


def user_permissoes(request):
    if not request.session.get('usuario_id'):
        return {}
    ctx = {
        "user_permissoes": get_usuario_permissoes(request),
    }
    if request.session.get('tipo_usuario') == 'colaborador':
        from rh.acesso import contexto_colaborador
        ctx.update(contexto_colaborador(request))
    return ctx
