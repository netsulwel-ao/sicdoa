import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import Usuario
from governanca.models import QuotaConfig, QuotaGerada, EstadoFinanceiro, Notificacao
from utils.email_utils import _enviar

class Command(BaseCommand):
    help = 'Gera quotas mensais para todos os despachantes ativos'

    def add_arguments(self, parser):
        parser.add_argument('--mes', type=int, help='Mês (1-12)')
        parser.add_argument('--ano', type=int, help='Ano')
        parser.add_argument('--force', action='store_true', help='Regenerar mesmo se já existir')

    def handle(self, *args, **options):
        hoje = timezone.now()
        mes = options.get('mes') or hoje.month
        ano = options.get('ano') or hoje.year
        config = QuotaConfig.objects.filter(ano=ano, mes=mes).first()
        if not config:
            self.stderr.write(f'Sem configuração de quota para {mes:02d}/{ano}')
            return
        despachantes = Usuario.objects.filter(papel='Despachante Oficial', status='Ativo')
        criadas = 0
        for d in despachantes:
            if QuotaGerada.objects.filter(despachante=d, ano=ano, mes=mes).exists():
                if options.get('force'):
                    QuotaGerada.objects.filter(despachante=d, ano=ano, mes=mes).delete()
                else:
                    continue
            q = QuotaGerada.objects.create(
                despachante=d, ano=ano, mes=mes,
                valor=config.valor, data_vencimento=config.data_vencimento,
            )
            ef, _ = EstadoFinanceiro.objects.get_or_create(despachante=d, defaults={'estado': 'Irregular'})
            if ef.estado == 'Regular':
                ef.estado = 'Irregular'
                ef.save()
            multa_str = f' Multa de {config.multa_percentual}%/dia após vencimento.' if config.multa_percentual else ''
            Notificacao.objects.create(
                usuario=d, tipo='quota_gerada',
                titulo=f'Quota de {mes:02d}/{ano}',
                mensagem=f'Foi gerada a sua quota no valor de Kz {config.valor}. Vencimento: {config.data_vencimento}.{multa_str}',
                link='/governanca/quotas/',
            )
            if d.email:
                _enviar('Quota Associativa Gerada',
                    f'Olá {d.nome},\n\nA sua quota de {mes:02d}/{ano} no valor de Kz {config.valor} foi gerada.\n'
                    f'Data de vencimento: {config.data_vencimento}\n'
                    f'{f"Multa de {config.multa_percentual}%/dia após o vencimento.\n" if config.multa_percentual else ""}'
                    f'\nAceda ao sistema para pagar.\n\nCDOA Angola',
                    None, [d.email])
            criadas += 1
        self.stdout.write(f'Geradas {criadas} quotas para {mes:02d}/{ano}')
