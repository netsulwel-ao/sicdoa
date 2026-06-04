from users.models import Usuario
from users.permissoes import get_usuario_permissoes


def cargos_mesa(request):
    data = {
        'is_membro_mesa': False,
        'is_secretario_mesa': False,
        'cargo_mesa_funcao': None,
        'user_permissoes': set(),
    }
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    if usuario_id:
        if papel == 'Administrador':
            data['is_membro_mesa'] = True
        else:
            usuario = Usuario.objects.filter(pk=usuario_id).first()
            if usuario and (usuario.has_cargo('secretario') or usuario.has_cargo('vice-secretario')):
                data['is_membro_mesa'] = True
                data['is_secretario_mesa'] = True
        data['user_permissoes'] = get_usuario_permissoes(request)
    return data
