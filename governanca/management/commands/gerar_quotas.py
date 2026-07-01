import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import Usuario
from governanca.models import TipoQuota, QuotaConfig, QuotaGerada, HistoricoQuota, Notificacao
from utils.email_utils import _enviar


def _periodo(tipo_slug, ano, mes=None):
    if tipo_slug == 'mensal' and mes:
        _, ultimo = calendar.monthrange(ano, mes)
        return date(ano, mes, 1), date(ano, mes, ultimo)
    if tipo_slug == 'trimestral':
        trimestre = (mes - 1) // 3 if mes else 1
        mes_ini = trimestre * 3 + 1
        mes_fim = mes_ini + 2
        _, ultimo = calendar.monthrange(ano, mes_fim)
        return date(ano, mes_ini, 1), date(ano, mes_fim, ultimo)
    if tipo_slug == 'semestral':
        semestre = 1 if (not mes or mes <= 6) else 2
        mes_ini = 1 if semestre == 1 else 7
        mes_fim = 6 if semestre == 1 else 12
        _, ultimo = calendar.monthrange(ano, mes_fim)
        return date(ano, mes_ini, 1), date(ano, mes_fim, ultimo)
    if tipo_slug == 'anual':
        return date(ano, 1, 1), date(ano, 12, 31)
    hoje = timezone.now().date()
    return hoje, hoje + timedelta(days=30)


class Command(BaseCommand):
    help = 'Gera quotas para todos os despachantes ativos por tipo (NÃO altera EstadoFinanceiro)'

    def add_arguments(self, parser):
        parser.add_argument('--mes', type=int, help='Mês (1-12)')
        parser.add_argument('--ano', type=int, help='Ano')
        parser.add_argument('--tipo', type=str, default='mensal', help='Slug do tipo de quota (padrão: mensal)')
        parser.add_argument('--force', action='store_true', help='Regenerar mesmo se já existir')

    def handle(self, *args, **options):
        hoje = timezone.now()
        mes = options.get('mes') or hoje.month
        ano = options.get('ano') or hoje.year
        tipo = TipoQuota.objects.filter(slug=options['tipo']).first()
        if not tipo:
            self.stderr.write(f'Tipo de quota "{options["tipo"]}" não encontrado')
            return

        slug = tipo.slug
        config = None
        if slug == 'mensal':
            config = QuotaConfig.objects.filter(ano=ano, mes=mes).first()
        elif slug in ('trimestral', 'semestral', 'anual'):
            config = QuotaConfig.objects.filter(tipo=tipo, ano=ano).first()
        elif slug == 'extraordinaria':
            config = QuotaConfig.objects.filter(tipo=tipo, ano=ano).first()
        if not config:
            self.stderr.write(f'Sem configuração de quota para {slug} {mes:02d}/{ano}')
            return

        periodo_ini, periodo_fim = _periodo(slug, ano, mes)

        despachantes = Usuario.objects.filter(papel='Despachante Oficial', status='Ativo')
        criadas = 0
        hoje_dt = timezone.now().date()
        seq = QuotaGerada.objects.filter(ano=ano, mes=mes, tipo=tipo).count() + 1
        slug_tipo = tipo.slug.upper()

        for d in despachantes:
            filtro = {'despachante': d, 'tipo': tipo}
            if slug == 'mensal':
                filtro['ano'] = ano
                filtro['mes'] = mes
            else:
                filtro['periodo_inicio'] = periodo_ini
            if QuotaGerada.objects.filter(**filtro).exists():
                if options.get('force'):
                    QuotaGerada.objects.filter(**filtro).delete()
                else:
                    continue
            descricao_map = {
                'mensal': f'{tipo.nome} {mes:02d}/{ano}',
                'trimestral': f'{tipo.nome} {periodo_ini:%b}-{periodo_fim:%b}/{ano}',
                'semestral': f'{tipo.nome} {periodo_ini:%b}-{periodo_fim:%b}/{ano}',
                'anual': f'{tipo.nome} {ano}',
                'extraordinaria': f'{tipo.nome} {hoje:%d/%m/%Y}',
            }
            descricao = descricao_map.get(slug, f'{tipo.nome} {mes:02d}/{ano}')
            referencia = f'QUOTA-{slug_tipo}-{mes:02d}-{ano}-{seq:05d}'
            seq += 1
            kwargs = {
                'despachante': d, 'tipo': tipo, 'ano': ano,
                'descricao': descricao,
                'valor': config.valor,
                'valor_original': config.valor,
                'valor_total': config.valor,
                'data_vencimento': config.data_vencimento,
                'data_envio': hoje_dt,
                'referencia': referencia,
                'periodo_inicio': periodo_ini, 'periodo_fim': periodo_fim,
            }
            if slug == 'mensal':
                kwargs['mes'] = mes
            q = QuotaGerada.objects.create(**kwargs)
            HistoricoQuota.objects.create(
                membro=d, quota=q, pagamento=None,
                acao='QUOTA_GERADA',
                descricao=f'Quota gerada automaticamente. Config: {descricao}. Referência: {referencia}',
            )
            multa_str = f' Multa de {config.multa_percentual}%/dia após vencimento.' if config.multa_percentual else ''
            carencia_str = f' Período de carência: {config.dias_carencia} dias.' if config.dias_carencia else ''
            link = '/governanca/quotas/'
            Notificacao.objects.create(
                usuario=d, tipo='quota_gerada',
                titulo=descricao,
                mensagem=f'Foi gerada a sua {descricao} no valor de Kz {config.valor}. Vencimento: {config.data_vencimento}.{multa_str}{carencia_str}',
                link=link,
            )
            if d.email:
                multa_msg = f'Multa de {config.multa_percentual}%/dia após o vencimento.\n' if config.multa_percentual else ''
                carencia_msg = f'Período de carência de {config.dias_carencia} dias.\n' if config.dias_carencia else ''
                corpo = (
                    f'Olá {d.nome},\n\nA sua {descricao} no valor de Kz {config.valor} foi gerada.\n'
                    f'Data de vencimento: {config.data_vencimento}\n'
                    f'{multa_msg}{carencia_msg}'
                    '\nAceda ao sistema para pagar.\n\nCDOA Angola'
                )
                _enviar('Quota Associativa Gerada', corpo, None, [d.email])
            criadas += 1
        self.stdout.write(f'Geradas {criadas} quotas {tipo.nome} para {mes:02d}/{ano}')
