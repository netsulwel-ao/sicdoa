import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

def safe_cache_key(*parts):
    return ':'.join(str(p).replace(' ', '_') for p in parts if p is not None)

def cache_get_or_set(key, func, timeout=300, version=None):
    cached = cache.get(key, version=version)
    if cached is not None:
        return cached
    data = func()
    cache.set(key, data, timeout=timeout, version=version)
    return data

def cache_invalidate(pattern):
    try:
        from django_redis import get_redis_connection
        r = get_redis_connection('default')
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        cache.clear()

def cache_invalidate_prefix(prefix):
    cache_invalidate(f'*{prefix}*')

def cache_invalidate_user_prefix(user_id, prefix):
    cache_invalidate(f'*:{prefix}:{user_id}:*')
    cache_invalidate(f'*:{prefix}_{user_id}*')
