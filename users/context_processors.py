from .permissoes import get_usuario_permissoes


def user_permissoes(request):
    if not request.session.get('usuario_id'):
        return {}
    return {
        "user_permissoes": get_usuario_permissoes(request),
    }
