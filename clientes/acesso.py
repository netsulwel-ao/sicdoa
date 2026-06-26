from django.db.models import Q
from users.permissoes import get_usuario_permissoes


def escopo_cliente(request, queryset):
    """
    Filtra Cliente conforme o papel e permissões do usuário logado.

    - Administrador / 'admin' → vê tudo (sem filtro)
    - Colaborador com filial_id definido → vê só clientes da sua filial (scoping inteligente)
    - Colaborador sem filial_id (sede) → vê clientes da sua banca
    - Despachante (sessão) → vê clientes da sua banca
    """
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return queryset
    perm_set = get_usuario_permissoes(request)
    if 'admin' in perm_set:
        return queryset
    tipo = request.session.get('tipo_usuario')
    if tipo == 'colaborador':
        from rh.models import Colaborador
        col_id = request.session.get('colaborador_id')
        if col_id:
            try:
                col = Colaborador.objects.only('banca_id', 'filial_id').get(pk=col_id, estado='Ativo')
                # Scoping inteligente: se colaborador está alocado a uma filial,
                # vê apenas dados dessa filial (independentemente das permissões)
                if col.filial_id:
                    return queryset.filter(banca_id=col.banca_id, filial_id=col.filial_id)
                return queryset.filter(banca_id=col.banca_id)
            except Colaborador.DoesNotExist:
                return queryset.none()
        return queryset.none()
    banca_id = request.session.get('banca_id')
    if banca_id:
        return queryset.filter(banca_id=banca_id)
    return queryset.filter(usuario_id=request.session.get('usuario_id'))
