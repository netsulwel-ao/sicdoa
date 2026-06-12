from users.models import Usuario
from users.permissoes import get_usuario_permissoes
from rh.models import CargoMesa


def cargos_mesa(request):
    data = {
        'is_membro_mesa': False,
        'is_secretario_mesa': False,
        'cargo_mesa_funcao': None,
        'user_permissoes': set(),
        'tem_banca': False,
    }
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    if usuario_id:
        from users.permissoes import _is_admin_ou_acesso_total
        if _is_admin_ou_acesso_total(request):
            data['is_membro_mesa'] = True
        else:
            cargo_mesa = CargoMesa.objects.filter(usuario_id=usuario_id).first()
            if cargo_mesa:
                data['is_membro_mesa'] = True
                data['cargo_mesa_funcao'] = cargo_mesa.funcao
                if cargo_mesa.funcao in ('Secretário', '1º Secretário', '2º Secretário', 'Vice-Presidente'):
                    data['is_secretario_mesa'] = True
        data['user_permissoes'] = get_usuario_permissoes(request)
        if papel in ('Administrador', 'Despachante Oficial', 'Operador') or 'admin' in data['user_permissoes']:
            from .models import Banca
            data['tem_banca'] = Banca.objects.filter(
                usuario_id=usuario_id, ativa=True
            ).exists()
        else:
            data['tem_banca'] = False
    return data
