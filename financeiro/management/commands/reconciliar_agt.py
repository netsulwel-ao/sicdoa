"""Reconcilia o estado das faturas eletrónicas pendentes com a AGT.

Consulta o serviço ``obterEstado`` para os documentos em estado "Enviada AGT"
e atualiza o estado local quando a AGT já devolveu a validação. Serve de
mecanismo de segurança para os casos em que o callback assíncrono não chega.
"""

from django.core.management.base import BaseCommand

from financeiro import agt_service
from financeiro.models import ConfiguracaoAGT, FaturaEletronica


class Command(BaseCommand):
    help = "Consulta a AGT (obterEstado) e sincroniza o estado das faturas pendentes."

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=100,
                            help='Número máximo de faturas a consultar (padrão: 100).')
        parser.add_argument('--banca', type=int, default=None,
                            help='Restringe a reconciliação a uma banca (ID).')

    def handle(self, *args, **options):
        limite = options['limite']
        banca_id = options['banca']

        qs = (
            FaturaEletronica.objects
            .filter(estado='Enviada AGT', request_id__isnull=False)
            .exclude(request_id='')
            .select_related('cliente')
            .order_by('data_envio_agt', 'pk')
        )
        if banca_id:
            qs = qs.filter(banca_id=banca_id)

        faturas = list(qs[:limite])
        if not faturas:
            self.stdout.write('Nenhuma fatura pendente de reconciliação.')
            return

        self.stdout.write(f'A reconciliar {len(faturas)} fatura(s)...')

        config_cache = {}
        alteradas = 0
        falhas = 0

        for i, fatura in enumerate(faturas, 1):
            if fatura.banca_id not in config_cache:
                config_cache[fatura.banca_id] = ConfiguracaoAGT.obter(fatura.banca_id)
            config = config_cache[fatura.banca_id]

            try:
                resultado = agt_service.reconciliar_fatura(fatura, config=config)
            except agt_service.AGTErro as exc:
                falhas += 1
                self.stderr.write(f'  [{i}/{len(faturas)}] {fatura.numero_fatura}: erro — {exc}')
                continue

            prefixo = f'  [{i}/{len(faturas)}] {fatura.numero_fatura}:'
            if resultado.get('alterado'):
                alteradas += 1
                self.stdout.write(self.style.WARNING(
                    f'{prefixo} {resultado.get("estado")}'
                ))
            else:
                self.stdout.write(f'{prefixo} {resultado.get("motivo")}')

        self.stdout.write(self.style.SUCCESS(
            f'Reconciliação concluída: {alteradas} atualizada(s), {falhas} falha(s) '
            f'de {len(faturas)} consultada(s).'
        ))
