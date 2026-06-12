from django.core.management.base import BaseCommand
from clientes.models import Cliente
from financeiro.models import (
    FacturaCliente, ReciboCliente,
    NotaCredito, NotaDebito, FacturaRecibo,
)
from django.db.models import Sum, F


class Command(BaseCommand):
    help = "Recalcula o saldo_conta_corrente e o valor_pago das facturas"

    def handle(self, *args, **options):
        clientes = Cliente.objects.all()
        total = clientes.count()
        for i, cliente in enumerate(clientes, 1):
            saldo = 0.0

            # Facturas (não canceladas) debitam
            facturas = FacturaCliente.objects.filter(cliente=cliente).exclude(estado='Cancelada')
            total_facturas = facturas.aggregate(s=Sum('valor_total'))['s'] or 0
            saldo -= float(total_facturas)

            # Recibos (não cancelados) creditam
            recibos = ReciboCliente.objects.filter(cliente=cliente).exclude(estado='Cancelado')
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

        self.stdout.write("\nA recalcular valor_pago das facturas...")
        facturas = FacturaCliente.objects.exclude(estado='Cancelada')
        total_f = facturas.count()
        for j, factura in enumerate(facturas.iterator(), 1):
            total_pago = float(factura.recibos.filter(factura=factura).exclude(estado='Cancelado').aggregate(
                total=Sum('valor_recebido'))['total'] or 0.0)
            total_pago += float(factura.facturas_recibo.filter(factura=factura, estado='Paga').aggregate(
                total=Sum('valor'))['total'] or 0.0)
            factura.valor_pago = total_pago
            if total_pago >= float(factura.valor_total):
                factura.estado = 'Paga'
            elif total_pago > 0:
                factura.estado = 'Parcialmente Paga'
            else:
                factura.estado = 'Pendente'
            factura.save(update_fields=['valor_pago', 'estado'])
            self.stdout.write(f"  [{j}/{total_f}] Factura {factura.numero_factura}: valor_pago={total_pago:.2f}, estado={factura.estado}")

        self.stdout.write(self.style.SUCCESS(f"Saldo e valor_pago recalculados para {total} clientes e {total_f} facturas."))
