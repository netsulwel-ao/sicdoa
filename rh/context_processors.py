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
        'tem_banca_central': False,
    }
    usuario_id = request.session.get('usuario_id')
    papel_sessao = request.session.get('usuario', {}).get('papel', '')
    papel_display_sessao = request.session.get('usuario', {}).get('papel_display', '')
    if usuario_id:
        permissoes = get_usuario_permissoes(request)
        data['user_permissoes'] = permissoes

        from users.permissoes import _is_admin_ou_acesso_total
        if _is_admin_ou_acesso_total(request) or 'ser_membro_mesa' in permissoes:
            data['is_membro_mesa'] = True

        cargo_mesa = CargoMesa.objects.filter(usuario_id=usuario_id).first()
        if cargo_mesa:
            data['cargo_mesa_funcao'] = cargo_mesa.funcao
            if cargo_mesa.funcao in ('Secretário', '1º Secretário', '2º Secretário', 'Vice-Presidente'):
                data['is_secretario_mesa'] = True

        data['papel'] = papel_sessao
        data['papel_display'] = papel_display_sessao or papel_sessao
        if papel_sessao in ('Administrador', 'Despachante Oficial') or 'admin' in data['user_permissoes']:
            from .models import Banca
            data['tem_banca'] = Banca.objects.filter(
                usuario_id=usuario_id, ativa=True
            ).exists()
        else:
            data['tem_banca'] = False

        if papel_sessao == 'Administrador':
            from .models import BancaCentral
            data['tem_banca_central'] = BancaCentral.objects.filter(ativa=True).exists()
    return data
