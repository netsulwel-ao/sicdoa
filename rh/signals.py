from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.cache_utils import cache_invalidate_prefix

from .models import Banca, FilialBanca, Colaborador, Vaga, Subsidio


@receiver(post_save, sender=Banca)
@receiver(post_delete, sender=Banca)
def invalida_cache_banca(sender, instance, **kwargs):
    cache_invalidate_prefix('admin_bancas')
    cache_invalidate_prefix('admin_despachantes')


@receiver(post_save, sender=FilialBanca)
@receiver(post_delete, sender=FilialBanca)
def invalida_cache_filial(sender, instance, **kwargs):
    cache_invalidate_prefix('admin_bancas')


@receiver(post_save, sender=Colaborador)
@receiver(post_delete, sender=Colaborador)
def invalida_cache_colaborador(sender, instance, **kwargs):
    if hasattr(instance, 'banca') and instance.banca:
        cache_invalidate_prefix('admin_despachantes')


@receiver(post_save, sender=Vaga)
@receiver(post_delete, sender=Vaga)
def invalida_cache_vaga(sender, instance, **kwargs):
    pass


@receiver(post_save, sender=Subsidio)
@receiver(post_delete, sender=Subsidio)
def invalida_cache_subsidio(sender, instance, **kwargs):
    pass