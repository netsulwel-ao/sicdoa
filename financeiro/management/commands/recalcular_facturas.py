from django.core.management.base import BaseCommand
from decimal import Decimal
from financeiro.models import FacturaCliente


class Command(BaseCommand):
    help = 'Recalcula IVA (14% sobre subtotal), retencao e valor_total das Facturas existentes'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Mostra o que seria feito sem alteracoes')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        facturas = FacturaCliente.objects.all()
        total = facturas.count()
        self.stdout.write(f'Total de facturas a processar: {total}')
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nenhuma alteracao sera feita'))

        atualizadas = 0
        for ft in facturas:
            subtotal = ft.honorarios_despachante + ft.taxas_aduaneiras + ft.emolumentos + ft.despesas_operacionais + ft.outros_encargos
            novo_iva = (subtotal * Decimal('0.14')).quantize(Decimal('0.01'))
            # Copiar retencao da requisicao vinculada, se existir
            if ft.requisicao_fundo:
                novo_retencao = ft.requisicao_fundo.retencao or Decimal('0')
            else:
                novo_retencao = Decimal('0')
            novo_total = subtotal + novo_iva + novo_retencao

            if dry_run:
                self.stdout.write(
                    f'{ft.numero_factura}: subtotal={subtotal} | iva={ft.iva}->{novo_iva} | '
                    f'ret={ft.retencao}->{novo_retencao} | total={ft.valor_total}->{novo_total}'
                )
            else:
                ft.iva = novo_iva
                ft.retencao = novo_retencao
                ft.valor_total = novo_total
                ft.save(update_fields=['iva', 'retencao', 'valor_total'])
                self.stdout.write(
                    f'{ft.numero_factura}: IVA={novo_iva} Retencao={novo_retencao} Total={novo_total}'
                )
            atualizadas += 1

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'[DRY-RUN] Seriam atualizadas {atualizadas} facturas'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{atualizadas} facturas atualizadas com sucesso'))
