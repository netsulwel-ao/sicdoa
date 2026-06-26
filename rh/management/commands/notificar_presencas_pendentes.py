"""
Management command para notificar responsáveis sobre presenças/férias pendentes
e alertar sobre SLA excedido (pedidos pendentes há mais de N dias).
Uso: python manage.py notificar_presencas_pendentes [--dias 3] [--banca-slug X]
"""
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db.models import Count
from rh.models import Banca, RegistoPresenca, PedidoFerias
from rh.views import _encontrar_responsavel_aprovacao
from rh.notificacoes import notificar_presenca_pendente, notificar_ferias_pendente


class Command(BaseCommand):
    help = 'Notifica responsáveis sobre presenças/férias pendentes e alerta SLA'

    def add_arguments(self, parser):
        parser.add_argument('--dias', type=int, default=3,
                            help='Dias para considerar SLA excedido (padrão: 3)')
        parser.add_argument('--banca-slug', type=str, help='Slug da banca. Padrão: todas')
        parser.add_argument('--notificar', action='store_true',
                            help='Enviar notificações para os responsáveis')

    def handle(self, *args, **options):
        sla_dias = options['dias']
        hoje = date.today()
        limite_sla = hoje - timedelta(days=sla_dias)

        bancas = Banca.objects.filter(ativa=True)
        if options['banca_slug']:
            bancas = bancas.filter(slug=options['banca_slug'])

        total_notificados = 0
        total_sla = 0

        for banca in bancas:
            cols = banca.colaboradores.filter(estado='Ativo')
            col_ids = cols.values_list('id', flat=True)

            # Presenças pendentes há mais de sla_dias
            presencas_pendentes = RegistoPresenca.objects.filter(
                colaborador_id__in=col_ids,
                estado='Pendente',
                criado_em__lt=limite_sla,
            ).select_related('colaborador')

            for reg in presencas_pendentes:
                responsavel = _encontrar_responsavel_aprovacao(banca, reg.colaborador)
                if responsavel and options['notificar']:
                    notificar_presenca_pendente(reg, banca, responsavel)
                    total_notificados += 1
                dias_pendente = (hoje - reg.criado_em.date()).days if reg.criado_em else 0
                self.stdout.write(
                    f'SLA: Presença de {reg.colaborador.nome} '
                    f'({reg.data}) pendente há {dias_pendente} dias.'
                )
                total_sla += 1

            # Pedidos de férias pendentes há mais de sla_dias
            ferias_pendentes = PedidoFerias.objects.filter(
                colaborador_id__in=col_ids,
                estado='Pendente',
                criado_em__lt=limite_sla,
            ).select_related('colaborador')

            for pedido in ferias_pendentes:
                responsavel = _encontrar_responsavel_aprovacao(banca, pedido.colaborador)
                if responsavel and options['notificar']:
                    notificar_ferias_pendente(pedido, banca, responsavel)
                    total_notificados += 1
                dias_pendente = (hoje - pedido.criado_em.date()).days if pedido.criado_em else 0
                self.stdout.write(
                    f'SLA: Férias de {pedido.colaborador.nome} '
                    f'({pedido.data_inicio} a {pedido.data_fim}) pendente há {dias_pendente} dias.'
                )
                total_sla += 1

        if total_sla:
            self.stdout.write(self.style.WARNING(
                f'{total_sla} registo(s) com SLA excedido. '
                f'{total_notificados} notificação(ões) enviada(s).'
            ))
        else:
            self.stdout.write(self.style.SUCCESS('Nenhum registo com SLA excedido.'))
