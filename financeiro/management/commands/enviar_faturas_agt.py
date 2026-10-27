"""Processa a fila de faturas eletrónicas e submete-as à AGT.

O envio é feito fora do pedido HTTP: o utilizador coloca o documento em fila
(estado ``Em Fila``) e este comando, agendado no APScheduler, efectua o registo
na AGT. Falhas transitórias são repetidas até ``MAX_TENTATIVAS``.
"""
from django.core.management.base import BaseCommand

from financeiro import agt_service
from financeiro.models import ConfiguracaoAGT, FaturaEletronica

MAX_TENTATIVAS = 5


class Command(BaseCommand):
    help = "Envia à AGT as faturas eletrónicas em fila (estado 'Em Fila')."

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=50,
                            help='Número máximo de documentos a processar (padrão: 50).')
        parser.add_argument('--banca', type=int, default=None,
                            help='Restringe o processamento a uma banca.')

    def handle(self, *args, **options):
        faturas = (
            FaturaEletronica.objects
            .filter(estado='Em Fila')
            .select_related('cliente', 'factura_cliente', 'requisicao_fundo',
                            'documento_origem_ref')
            .order_by('data_emissao')
        )
        if options['banca']:
            faturas = faturas.filter(banca_id=options['banca'])
        faturas = list(faturas[:options['limite']])

        if not faturas:
            self.stdout.write('Nenhuma fatura em fila para envio.')
            return

        cache_config = {}
        enviadas = rejeitadas = adiadas = 0
        for fatura in faturas:
            if fatura.banca_id not in cache_config:
                cache_config[fatura.banca_id] = ConfiguracaoAGT.obter(fatura.banca_id)
            resultado = agt_service.enviar_fatura(fatura, cache_config[fatura.banca_id])

            if resultado['ok']:
                if resultado['estado'] == 'Rejeitada AGT':
                    rejeitadas += 1
                else:
                    enviadas += 1
                self.stdout.write(f'  {fatura.numero_fatura}: {resultado["motivo"]}')
                continue

            # Falha (transitória ou de configuração): conta a tentativa.
            fatura.tentativas_envio = (fatura.tentativas_envio or 0) + 1
            if fatura.tentativas_envio >= MAX_TENTATIVAS:
                fatura.estado = 'Rascunho'
                fatura.save(update_fields=['tentativas_envio', 'estado'])
                self.stderr.write(
                    f'  {fatura.numero_fatura}: limite de tentativas atingido '
                    f'({resultado["motivo"]}) → devolvida a Rascunho.'
                )
            else:
                fatura.save(update_fields=['tentativas_envio'])
                adiadas += 1
                self.stderr.write(f'  {fatura.numero_fatura}: {resultado["motivo"]}')

        self.stdout.write(
            f'Fila processada: {enviadas} enviada(s), {rejeitadas} rejeitada(s), '
            f'{adiadas} adiada(s).'
        )
