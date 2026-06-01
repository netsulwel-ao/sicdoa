from celery import shared_task
from utils.cache_utils import cache_invalidate_prefix


@shared_task
def invalidar_cache_du(usuario_id=None):
    if usuario_id:
        cache_invalidate_prefix(f'du_lista_{usuario_id}')
    else:
        cache_invalidate_prefix('du_lista')


@shared_task
def invalidar_cache_vinhetas(cedula):
    from django.core.cache import cache
    cache.delete(f'vinhetas_{cedula}')


@shared_task
def invalidar_cache_pauta():
    from django.core.cache import cache
    cache.delete_pattern('pauta_api_*')
