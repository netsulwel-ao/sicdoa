from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from utils.cache_utils import cache_invalidate_prefix

from .models import (
    Assembleia, PautaVotacao, Notificacao, AtaDigital,
    DocumentoAssembleia, QuotaConfig, QuotaGerada, PagamentoQuota,
    VotacaoConsulta, MensagemChat, Convocatoria,
)


@receiver(post_save, sender=Assembleia)
@receiver(post_delete, sender=Assembleia)
def invalida_cache_assembleia(sender, **kwargs):
    cache_invalidate_prefix('lista_assembleias')


@receiver(post_save, sender=Notificacao)
@receiver(post_delete, sender=Notificacao)
def invalida_cache_notificacao(sender, instance, **kwargs):
    pass


@receiver(post_save, sender=AtaDigital)
@receiver(post_delete, sender=AtaDigital)
def invalida_cache_atas(sender, **kwargs):
    cache_invalidate_prefix('repositorio_atas')


@receiver(post_save, sender=DocumentoAssembleia)
@receiver(post_delete, sender=DocumentoAssembleia)
def invalida_cache_documentos(sender, **kwargs):
    cache_invalidate_prefix('repositorio_atas')


@receiver(post_save, sender=QuotaConfig)
@receiver(post_save, sender=QuotaGerada)
@receiver(post_delete, sender=QuotaGerada)
@receiver(post_save, sender=PagamentoQuota)
@receiver(post_delete, sender=PagamentoQuota)
def invalida_cache_quotas(sender, **kwargs):
    pass