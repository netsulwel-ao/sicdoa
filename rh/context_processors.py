from .models import CargoMesa


def cargos_mesa(request):
    data = {
        'is_membro_mesa': False,
        'is_secretario_mesa': False,
        'cargo_mesa_funcao': None,
    }
    usuario_id = request.session.get('usuario_id')
    if usuario_id:
        cargo = CargoMesa.objects.filter(usuario_id=usuario_id).first()
        if cargo:
            data['is_membro_mesa'] = True
            data['cargo_mesa_funcao'] = cargo.funcao
            data['is_secretario_mesa'] = cargo.funcao in (
                '1º Secretário', '2º Secretário', 'Secretário', 'Vice-Presidente',
            )
    return data
