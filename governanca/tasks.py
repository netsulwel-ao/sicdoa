from celery import shared_task
from django.core.cache import cache
from utils.cache_utils import cache_invalidate_prefix, cache_invalidate_user_prefix


@shared_task
def invalidar_cache_governanca(pattern=None):
    cache_invalidate_prefix('dash_governanca')
    cache_invalidate_prefix('lista_assembleias')
    cache_invalidate_prefix('dash_quotas')
    cache_invalidate_prefix('repositorio_atas')
    cache_invalidate_prefix('consulta_lista')


@shared_task
def invalidar_cache_assembleia(assembleia_id):
    cache_invalidate_prefix(f'dash_governanca')
    cache_invalidate_prefix(f'lista_assembleias')


@shared_task
def invalidar_cache_quotas():
    cache_invalidate_prefix('dash_quotas')
    cache_invalidate_prefix('relatorio_quotas')


@shared_task
def notificar_utilizadores_task(usuario_ids, tipo, titulo, mensagem='', link=''):
    from governanca.models import Notificacao
    from utils.cache_utils import cache_invalidate_prefix
    for uid in usuario_ids:
        Notificacao.objects.create(
            usuario_id=uid, tipo=tipo, titulo=titulo,
            mensagem=mensagem, link=link,
        )
        cache_invalidate_prefix(f'dash_governanca_{uid}')
