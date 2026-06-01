from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.cache_utils import cache_invalidate_prefix

from .models import DeclaracaoUnica


@receiver(post_save, sender=DeclaracaoUnica)
@receiver(post_delete, sender=DeclaracaoUnica)
def invalida_cache_du(sender, instance, **kwargs):
    cache_invalidate_prefix(f'du_lista_{instance.usuario_id}')
