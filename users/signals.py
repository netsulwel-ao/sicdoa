from datetime import timedelta
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Usuario


@receiver(post_save, sender=Usuario)
@transaction.atomic
def gerar_inscricao_auto(sender, instance, created, **kwargs):
    if not created:
        return
    if instance.papel != 'Despachante Oficial':
        return
    from governanca.models import TipoQuota, QuotaConfig, QuotaGerada, EstadoFinanceiro
    tipo = TipoQuota.objects.filter(slug='inscricao').first()
    if not tipo:
        return
    config = QuotaConfig.objects.filter(tipo=tipo, ano=timezone.now().year).first()
    valor = config.valor if config else 0
    vencimento = instance.created_at.date() + timedelta(days=30)
    if QuotaGerada.objects.filter(despachante=instance, tipo=tipo).exists():
        return
    QuotaGerada.objects.create(
        despachante=instance,
        tipo=tipo,
        descricao=f'{tipo.nome} — {instance.nome}',
        valor=valor,
        data_vencimento=vencimento,
        periodo_inicio=instance.created_at.date(),
        periodo_fim=vencimento,
    )
    EstadoFinanceiro.objects.get_or_create(despachante=instance, defaults={'estado': 'Irregular'})
