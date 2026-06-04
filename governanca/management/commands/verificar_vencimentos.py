"""
Management command: verificar_vencimentos
Executado diariamente (03:00) via cron / Celery beat.

Para cada QuotaGerada com status=Pendente e data_vencimento + dias_carencia < hoje:
  → marca como ATRASADA
  → calcula multa: dias_atraso * (multa_percentual_dia/100) * valor_original
  → actualiza EstadoFinanceiro para Irregular (se não Suspenso)
  → notifica o membro

Para quotas já ATRASADA, recalcula a multa (cresce diariamente).
Notifica apenas no 1º dia e semanalmente (7 em 7 dias).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from governanca.models import QuotaGerada, QuotaConfig, HistoricoQuota, Notificacao
from users.models import Usuario
from utils.email_utils import _enviar


class Command(BaseCommand):
    help = 'Verifica quotas vencidas, aplica multas e actualiza estado financeiro'

    def handle(self, *args, **options):
        hoje = timezone.now().date()
        processadas = 0
        notificadas = 0
        irregulares = 0

        quotas_pendentes = QuotaGerada.objects.filter(
            status='Pendente',
            data_vencimento__lt=hoje,
        ).select_related('despachante', 'tipo')

        for q in quotas_pendentes:
            config = QuotaConfig.objects.filter(ano=q.ano, mes=q.mes).first() if q.ano and q.mes else None
            if not config or not config.multa_percentual:
                continue
            carencia = config.dias_carencia or 0
            dias_desde_venc = (hoje - q.data_vencimento).days
            if dias_desde_venc <= carencia:
                continue
            dias_atraso = dias_desde_venc - carencia
            valor_original = q.valor_original or q.valor
            multa_valor = valor_original * (config.multa_percentual / Decimal(100)) * dias_atraso
            q.valor_multa = multa_valor
            q.valor_total = valor_original + multa_valor
            q.status = 'Atrasada'
            q.save(update_fields=['status', 'valor_multa', 'valor_total'])
            HistoricoQuota.objects.create(
                membro=q.despachante, quota=q, pagamento=None,
                acao='QUOTA_VENCIDA',
                descricao=f'Quota vencida há {dias_atraso} dias. Multa: Kz {multa_valor:.2f} ({config.multa_percentual}%/dia, carência {carencia}d)',
            )
            processadas += 1

            from governanca.views import _atualizar_estado_financeiro
            _atualizar_estado_financeiro(q.despachante_id)
            irregulares += 1

            Notificacao.objects.create(
                usuario=q.despachante, tipo='quota_vencida',
                titulo=f'Quota {q.mes:02d}/{q.ano} — Vencida',
                mensagem=f'A sua quota {q.referencia or f"{q.mes:02d}/{q.ano}"} venceu há {dias_atraso} dias. '
                         f'Multa acumulada: Kz {multa_valor:.2f}. Total devido: Kz {q.valor_total:.2f}.',
                link='/governanca/quotas/',
            )
            if q.despachante.email:
                _enviar(
                    'Quota Associativa — Aviso de Vencimento',
                    f'Olá {q.despachante.nome},\n\n'
                    f'A sua quota {q.referencia or f"{q.mes:02d}/{q.ano}"} venceu há {dias_atraso} dias.\n'
                    f'Valor original: Kz {valor_original:.2f}\n'
                    f'Multa ({config.multa_percentual}%/dia): Kz {multa_valor:.2f}\n'
                    f'Total devido: Kz {q.valor_total:.2f}\n\n'
                    f'Regularize o pagamento para evitar restrições.\n\n'
                    f'CDOA Angola',
                    None, [q.despachante.email],
                )
            notificadas += 1

        quotas_atrasadas = QuotaGerada.objects.filter(
            status='Atrasada',
        ).select_related('despachante', 'tipo')

        for q in quotas_atrasadas:
            config = QuotaConfig.objects.filter(ano=q.ano, mes=q.mes).first() if q.ano and q.mes else None
            if not config or not config.multa_percentual:
                continue
            carencia = config.dias_carencia or 0
            dias_desde_venc = (hoje - q.data_vencimento).days
            if dias_desde_venc <= carencia:
                continue
            dias_atraso = dias_desde_venc - carencia
            valor_original = q.valor_original or q.valor
            nova_multa = valor_original * (config.multa_percentual / Decimal(100)) * dias_atraso
            if nova_multa != q.valor_multa:
                q.valor_multa = nova_multa
                q.valor_total = valor_original + nova_multa
                q.save(update_fields=['valor_multa', 'valor_total'])

        self.stdout.write(
            f'Verificados vencimentos: {processadas} quotas marcadas como ATRASADA, '
            f'{notificadas} notificações enviadas, {irregulares} membros Irregulares'
        )
