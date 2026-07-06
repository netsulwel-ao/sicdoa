from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import RequisicaoFundo
from aduaneiro.models import DeclaracaoUnica


@receiver(post_save, sender=RequisicaoFundo)
def atualizar_status_du_apos_requisicao_aceite(sender, instance, created=False, **kwargs):
    """
    Quando uma RequisicaoFundo (Fatura Pró-forma) muda para 'Aceite'
    (cliente aceitou a proposta), atualiza a DU associada para 'Aprovada'.
    """
    try:
        if instance.estado == 'Aceite' and instance.total_geral > 0:
            du = instance.processo_aduaneiro
            if du and du.status == 'Submetida':
                du.status = 'Aprovada'
                du.data_aprovacao = timezone.now()
                du.save(update_fields=['status', 'data_aprovacao', 'updated_at'])
    except Exception as e:
        print(f"Erro ao atualizar status DU ao aceitar requisição: {str(e)}")
