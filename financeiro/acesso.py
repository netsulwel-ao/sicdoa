from django.db.models import Q, Model
from users.permissoes import get_usuario_permissoes


SCOPO_FILIAL_PERMS = {'gerir_filial'}


def _get_banca_filial(request):
    """
    Obtém (banca_id, filial_id, perm_set, is_admin) do request.
    Colaborador com filial_id definido fica escopeado a essa filial
    independentemente das permissões (scoping inteligente).
    """
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return None, None, None, True
    perm_set = get_usuario_permissoes(request)
    if 'admin' in perm_set:
        return None, None, None, True
    tipo = request.session.get('tipo_usuario')
    if tipo == 'colaborador':
        from rh.models import Colaborador
        col_id = request.session.get('colaborador_id')
        if col_id:
            try:
                col = Colaborador.objects.only('banca_id', 'filial_id').get(pk=col_id, estado='Ativo')
                filial_id = col.filial_id  # inteligente: se tiver filial, scope a ela
                return col.banca_id, filial_id, perm_set, False
            except Colaborador.DoesNotExist:
                return None, None, None, False
        return None, None, None, False
    banca_id = request.session.get('banca_id')
    if banca_id:
        return banca_id, None, perm_set, False
    uid = request.session.get('usuario_id')
    return None, None, None, uid is None


def _tem_escopo_filial(perm_set, filial_id):
    """True se o user tem filial_id definido OU alguma perm que limite à filial."""
    return bool(filial_id) or bool(
        (perm_set or set()) & SCOPO_FILIAL_PERMS
    )


def escopo_requisicao(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)


def escopo_factura_cliente(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)


def escopo_recibo_cliente(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)


def escopo_nota_credito(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)


def escopo_nota_debito(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)


def escopo_factura_recibo(request, queryset):
    banca_id, filial_id, perm_set, is_admin = _get_banca_filial(request)
    if is_admin:
        return queryset
    if banca_id is None:
        return queryset.none()
    if _tem_escopo_filial(perm_set, filial_id):
        return queryset.filter(banca_id=banca_id, filial_id=filial_id)
    return queryset.filter(banca_id=banca_id)
