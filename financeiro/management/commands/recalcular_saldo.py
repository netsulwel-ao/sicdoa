from django.core.management.base import BaseCommand
from clientes.models import Cliente
from financeiro.models import (
    FacturaCliente, ReciboCliente,
    NotaCredito, NotaDebito, FacturaRecibo,
)
from django.db.models import Sum, F


class Command(BaseCommand):
    help = "Recalcula o saldo_conta_corrente de todos os clientes a partir do zero"

    def handle(self, *args, **options):
        clientes = Cliente.objects.all()
        total = clientes.count()
        for i, cliente in enumerate(clientes, 1):
            saldo = 0.0

            # Facturas (não canceladas) debitam
            facturas = FacturaCliente.objects.filter(cliente=cliente).exclude(estado='Cancelada')
            total_facturas = facturas.aggregate(s=Sum('valor_total'))['s'] or 0
            saldo -= float(total_facturas)

            # Recibos creditam
            recibos = ReciboCliente.objects.filter(cliente=cliente)
            total_recibos = recibos.aggregate(s=Sum('valor_recebido'))['s'] or 0
            saldo += float(total_recibos)

            # Notas Crédito Aprovadas creditam
            nc = NotaCredito.objects.filter(cliente=cliente, estado='Aprovada')
            total_nc = nc.aggregate(s=Sum('valor_creditado'))['s'] or 0
            saldo += float(total_nc)

            # Notas Débito Aprovadas debitam
            nd = NotaDebito.objects.filter(cliente=cliente, estado='Aprovada')
            total_nd = nd.aggregate(s=Sum('valor'))['s'] or 0
            saldo -= float(total_nd)

            # Facturas-Recibo: impacto líquido zero (débito + crédito mesmo valor)
            # Apenas para confirmação, não alteramos o saldo

            Cliente.objects.filter(pk=cliente.pk).update(saldo_conta_corrente=saldo)

            self.stdout.write(
                f"[{i}/{total}] {cliente.nome:30s} "
                f"fact={float(total_facturas):>10.2f} "
                f"rec={float(total_recibos):>10.2f} "
                f"nc={float(total_nc):>8.2f} "
                f"nd={float(total_nd):>8.2f} "
                f"=> saldo={saldo:>10.2f}"
            )

        self.stdout.write(self.style.SUCCESS(f"Saldo recalculado para {total} clientes."))
