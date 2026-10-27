"""Processa a fila de callbacks (webhooks) pendentes da AGT.

O endpoint público guarda cada notificação em ``CallbackAGT`` antes de
responder. Este comando reprocessa os eventos que ficaram pendentes ou que
falharam, garantindo entrega pelo menos uma vez mesmo quando o processamento
imediato não é possível.
"""

from django.core.management.base import BaseCommand

from financeiro.agt_callbacks import processar_pendentes
from financeiro.models import CallbackAGT


class Command(BaseCommand):
    help = "Processa os callbacks da AGT pendentes na fila persistente."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limite', type=int, default=50,
            help='Número máximo de eventos a processar (padrão: 50).',
        )
        parser.add_argument(
            '--reprocessar-erros', action='store_true',
            help='Volta a colocar em fila os eventos em estado Erro.',
        )

    def handle(self, *args, **options):
        if options['reprocessar_erros']:
            repostos = (
                CallbackAGT.objects.filter(estado_processamento='Erro')
                .update(estado_processamento='Pendente', tentativas=0, erro='')
            )
            self.stdout.write(f'{repostos} evento(s) em erro repostos na fila.')

        resultado = processar_pendentes(limite=options['limite'])
        if not resultado['total']:
            self.stdout.write('Nenhum callback pendente.')
            return

        self.stdout.write(self.style.SUCCESS(
            f"Callbacks processados: {resultado['processados']} actualizado(s), "
            f"{resultado['ignorados']} ignorado(s), {resultado['erros']} erro(s) "
            f"de {resultado['total']} evento(s)."
        ))
