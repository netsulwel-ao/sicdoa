from celery import shared_task
from utils.cache_utils import cache_invalidate_prefix


@shared_task
def invalidar_cache_rh(pattern=None):
    cache_invalidate_prefix('dash_banca')
    cache_invalidate_prefix('admin_despachantes')
    cache_invalidate_prefix('admin_bancas')
    cache_invalidate_prefix('vagas_banca')
    cache_invalidate_prefix('colaboradores')
    cache_invalidate_prefix('salarios_banca')
    cache_invalidate_prefix('subsidios_banca')


@shared_task
def invalidar_cache_banca(banca_id):
    cache_invalidate_prefix(f'dash_banca_{banca_id}')
    cache_invalidate_prefix(f'vagas_banca_{banca_id}')
    cache_invalidate_prefix(f'colaboradores_{banca_id}')
    cache_invalidate_prefix(f'salarios_banca_{banca_id}')
    cache_invalidate_prefix(f'subsidios_banca_{banca_id}')
