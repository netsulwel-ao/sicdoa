from celery import shared_task
from utils.cache_utils import cache_invalidate_prefix


@shared_task
def invalidar_cache_rh(pattern=None):
    cache_invalidate_prefix('admin_despachantes')
    cache_invalidate_prefix('admin_bancas')


@shared_task
def invalidar_cache_banca(banca_id):
    pass