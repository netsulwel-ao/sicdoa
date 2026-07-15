"""
Corrige dados de quotas de despachantes oficiais:
  - Preenche ano/mes em QuotaGerada onde estiver None (a partir de periodo_inicio)
  - Corrige valor=0 quando existe QuotaConfig para o tipo
  - Coloca EstadoFinanceiro=Irregular -> Regular se NENHUMA quota esta efectivamente vencida
    (so tem quotas dentro do prazo de 30 dias)

Uso:  python manage.py corrigir_quotas_despachantes
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from governanca.models import QuotaGerada, EstadoFinanceiro, QuotaConfig


class Command(BaseCommand):
    help = 'Corrige quotas de inscricao e estado financeiro de despachantes'

    def handle(self, *args, **options):
        hoje = timezone.now().date()
        quotas_corrigidas = 0
        estados_corrigidos = 0

        # 1. Corrigir QuotaGerada com ano/mes None
        qs_none = QuotaGerada.objects.filter(ano__isnull=True)
        for q in qs_none:
            if q.periodo_inicio:
                QuotaGerada.objects.filter(pk=q.pk).update(
                    ano=q.periodo_inicio.year,
                    mes=q.periodo_inicio.month,
                )
                quotas_corrigidas += 1
                self.stdout.write(f'  [ANO/MES] #{q.pk} -> ano={q.periodo_inicio.year} mes={q.periodo_inicio.month}')
            else:
                self.stdout.write(f'  [SKIP] #{q.pk} sem periodo_inicio')

        # 2. Corrigir valor=0 quando existe config
        qs_zero = QuotaGerada.objects.filter(valor=0, status='Pendente')
        for q in qs_zero:
            config = QuotaConfig.objects.filter(tipo=q.tipo, ano=q.ano or hoje.year).first()
            if config and config.valor > 0:
                QuotaGerada.objects.filter(pk=q.pk).update(
                    valor=config.valor,
                    valor_original=config.valor,
                )
                quotas_corrigidas += 1
                self.stdout.write(f'  [VALOR] #{q.pk} -> Kz {config.valor}')

        # 3. Corrigir EstadoFinanceiro: se todas as quotas pendentes ainda estao dentro do prazo -> Regular
        for ef in EstadoFinanceiro.objects.filter(estado='Irregular'):
            pendentes = QuotaGerada.objects.filter(
                despachante_id=ef.despachante_id,
                status__in=['Pendente', 'Atrasada', 'Pendente Confirmacao'],
            )
            tem_vencida = pendentes.filter(data_vencimento__lt=hoje).exists()
            if not tem_vencida:
                EstadoFinanceiro.objects.filter(pk=ef.pk).update(estado='Regular')
                estados_corrigidos += 1
                self.stdout.write(f'  [ESTADO] despachante_id={ef.despachante_id} -> Regular (sem quotas vencidas)')

        self.stdout.write(self.style.SUCCESS(
            f'\nConcluido: {quotas_corrigidas} quotas corrigidas, {estados_corrigidos} estados corrigidos'
        ))
