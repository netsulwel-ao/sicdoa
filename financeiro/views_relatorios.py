import json
from collections import OrderedDict
from datetime import datetime, timedelta, date
from decimal import Decimal

from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Sum, Count, Case, When, Value, IntegerField, DecimalField, F
from django.db.models.functions import TruncMonth, ExtractYear, ExtractMonth
from django.utils import timezone
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator

from users.auth_decorators import requer_sessao_ativa
from users.models import Usuario
from clientes.models import Cliente
from .models import (
    RequisicaoFundo, FacturaCliente, ReciboCliente, NotaCredito, NotaDebito, FacturaRecibo, HistoricoFinanceiro
)
from .views import BaseContextMixin


class ReportPermissionMixin:
    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        papel = request.session.get('usuario', {}).get('papel', '')
        if papel not in self.allowed_roles:
            return redirect('financeiro:requisicao_lista')
        return super().dispatch(request, *args, **kwargs)


class ReportMixin(ReportPermissionMixin, BaseContextMixin):
    report_name = ''
    report_subtitle = ''
    active_sub = ''

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report_name'] = self.report_name
        context['report_subtitle'] = self.report_subtitle
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = self.active_sub
        return context

    def parse_dates(self):
        data_ini = self.request.GET.get('data_ini', '')
        data_fim = self.request.GET.get('data_fim', '')
        di = df = None
        if data_ini:
            try:
                di = datetime.strptime(data_ini, '%Y-%m-%d').date()
            except ValueError:
                pass
        if data_fim:
            try:
                df = datetime.strptime(data_fim, '%Y-%m-%d').date()
            except ValueError:
                pass
        return di, df, data_ini, data_fim

    def clientes_scope(self):
        filtro = self._get_user_filter_direct()
        if filtro:
            return Cliente.objects.filter(**filtro)
        return Cliente.objects.all()


# ── Relatórios Operacionais ────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioRequisicaoFundosView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Relatório de Requisição de Fundos'
    report_subtitle = 'Listagem de todas as requisições de fundos'
    active_sub = 'rel_requisicoes'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        estado = self.request.GET.get('estado', '')

        qs = RequisicaoFundo.objects.all()
        filtro = self._get_user_requisicao_filter()
        if filtro:
            qs = qs.filter(filtro)
        if di:
            qs = qs.filter(data__date__gte=di)
        if df:
            qs = qs.filter(data__date__lte=df)
        if estado:
            qs = qs.filter(estado=estado)

        total_solicitado = qs.aggregate(t=Sum('valor_solicitado'))['t'] or 0
        total_aprovado = qs.filter(estado='Aprovada').aggregate(t=Sum('valor_solicitado'))['t'] or 0

        context.update({
            'summary_cards': [
                {'label': 'Total de Requisições', 'value': qs.count(), 'color': 'primary'},
                {'label': 'Valor Total Solicitado', 'value': f'{total_solicitado:,.2f} Kz', 'color': 'warning'},
                {'label': 'Valor Aprovado', 'value': f'{total_aprovado:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['Nº', 'Cliente', 'Valor', 'Estado', 'Data', 'Solicitante'],
            'rows': [
                {
                    'cells': [r.numero_requisicao, r.cliente.nome, f'{r.valor_solicitado:,.2f}',
                              r.estado, r.data.strftime('%d/%m/%Y'), r.solicitante_nome],
                    'url': 'financeiro:requisicao_detalhe',
                    'pk': r.pk,
                }
                for r in qs.select_related('cliente')[:200]
            ],
            'filtro_estado': estado,
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
            'estados': ['Pendente', 'Em Aprovação', 'Aprovada', 'Rejeitada', 'Cancelada'],
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioFacturacaoView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Relatório de Facturação'
    report_subtitle = 'Resumo de todas as facturas emitidas'
    active_sub = 'rel_facturacao'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()

        clientes = self.clientes_scope()
        qs = FacturaCliente.objects.filter(cliente__in=clientes)
        if di:
            qs = qs.filter(data_emissao__date__gte=di)
        if df:
            qs = qs.filter(data_emissao__date__lte=df)

        total_facturado = qs.aggregate(t=Sum('valor_total'))['t'] or 0
        total_pago = qs.aggregate(t=Sum('valor_pago'))['t'] or 0
        pendentes = qs.filter(estado__in=['Pendente', 'Parcialmente Paga']).count()

        context.update({
            'summary_cards': [
                {'label': 'Total Facturado', 'value': f'{total_facturado:,.2f} Kz', 'color': 'primary'},
                {'label': 'Total Pago', 'value': f'{total_pago:,.2f} Kz', 'color': 'success'},
                {'label': 'Facturas Pendentes', 'value': pendentes, 'color': 'danger'},
            ],
            'columns': ['Factura', 'Cliente', 'Valor Total', 'Valor Pago', 'Estado', 'Emissão'],
            'rows': [
                {
                    'cells': [f.numero_factura, f.cliente.nome, f'{f.valor_total:,.2f}',
                              f'{f.valor_pago:,.2f}', f.estado, f.data_emissao.strftime('%d/%m/%Y')],
                    'url': 'financeiro:factura_detalhe',
                    'pk': f.pk,
                }
                for f in qs.select_related('cliente')[:200]
            ],
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioRecibosView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Relatório de Recibos'
    report_subtitle = 'Resumo de todos os recebimentos'
    active_sub = 'rel_recibos'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        fp = self.request.GET.get('forma_pagamento', '')

        clientes = self.clientes_scope()
        qs = ReciboCliente.objects.filter(cliente__in=clientes)
        if di:
            qs = qs.filter(data_pagamento__gte=di)
        if df:
            qs = qs.filter(data_pagamento__lte=df)
        if fp:
            qs = qs.filter(forma_pagamento=fp)

        total_recebido = qs.aggregate(t=Sum('valor_recebido'))['t'] or 0
        por_forma = qs.values('forma_pagamento').annotate(total=Sum('valor_recebido')).order_by('-total')

        context.update({
            'summary_cards': [
                {'label': 'Total de Recibos', 'value': qs.count(), 'color': 'primary'},
                {'label': 'Valor Total Recebido', 'value': f'{total_recebido:,.2f} Kz', 'color': 'success'},
                {'label': 'Formas de Pagamento', 'value': por_forma.count(), 'color': 'info'},
            ],
            'columns': ['Recibo', 'Cliente', 'Valor', 'Forma Pagamento', 'Data', 'Responsável'],
            'rows': [
                {
                    'cells': [r.numero_recibo, r.cliente.nome, f'{r.valor_recebido:,.2f}',
                              r.forma_pagamento, r.data_pagamento.strftime('%d/%m/%Y'),
                              r.utilizador_responsavel_nome],
                    'url': 'financeiro:recibo_detalhe',
                    'pk': r.pk,
                }
                for r in qs.select_related('cliente')[:200]
            ],
            'extra_tables': [
                {
                    'title': 'Recebimentos por Forma de Pagamento',
                    'columns': ['Forma de Pagamento', 'Total'],
                    'rows': [{'cells': [p['forma_pagamento'], f'{p["total"]:,.2f} Kz'], 'url': None, 'pk': None}
                             for p in por_forma],
                }
            ],
            'filtro_forma_pagamento': fp,
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
            'formas_pagamento': ReciboCliente.FORMAS_PAGAMENTO,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatoriosNotasHomeView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorios_notas_home.html'
    report_name = 'Relatórios de Notas'
    active_sub = 'rel_notas'


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioNotasCreditoView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Relatório de Notas de Crédito'
    report_subtitle = 'Resumo de todas as notas de crédito emitidas'
    active_sub = 'rel_notas_credito'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        estado = self.request.GET.get('estado', '')

        clientes = self.clientes_scope()
        qs = NotaCredito.objects.filter(cliente__in=clientes)
        if di:
            qs = qs.filter(data__gte=di)
        if df:
            qs = qs.filter(data__lte=df)
        if estado:
            qs = qs.filter(estado=estado)

        total_creditado = qs.aggregate(t=Sum('valor_creditado'))['t'] or 0
        aprovadas = qs.filter(estado='Aprovada').aggregate(t=Sum('valor_creditado'))['t'] or 0

        context.update({
            'summary_cards': [
                {'label': 'Total de NC', 'value': qs.count(), 'color': 'primary'},
                {'label': 'Valor Total Creditado', 'value': f'{total_creditado:,.2f} Kz', 'color': 'warning'},
                {'label': 'Valor Aprovado', 'value': f'{aprovadas:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['NC', 'Cliente', 'Factura', 'Valor', 'Estado', 'Data', 'Motivo'],
            'rows': [
                {
                    'cells': [n.numero_nota, n.cliente.nome, n.factura_relacionada.numero_factura,
                              f'{n.valor_creditado:,.2f}', n.estado, n.data.strftime('%d/%m/%Y'), n.motivo[:50]],
                    'url': 'financeiro:nota_credito_detalhe',
                    'pk': n.pk,
                }
                for n in qs.select_related('cliente', 'factura_relacionada')[:200]
            ],
            'filtro_estado': estado,
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
            'estados': ['Pendente', 'Aprovada', 'Rejeitada', 'Cancelada'],
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioNotasDebitoView(ReportMixin, TemplateView):
    allowed_roles = ['Despachante Oficial', 'Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Relatório de Notas de Débito'
    report_subtitle = 'Resumo de todas as notas de débito emitidas'
    active_sub = 'rel_notas_debito'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        estado = self.request.GET.get('estado', '')

        clientes = self.clientes_scope()
        qs = NotaDebito.objects.filter(cliente__in=clientes)
        if di:
            qs = qs.filter(data__gte=di)
        if df:
            qs = qs.filter(data__lte=df)
        if estado:
            qs = qs.filter(estado=estado)

        total_debitado = qs.aggregate(t=Sum('valor'))['t'] or 0
        aprovadas = qs.filter(estado='Aprovada').aggregate(t=Sum('valor'))['t'] or 0

        context.update({
            'summary_cards': [
                {'label': 'Total de ND', 'value': qs.count(), 'color': 'primary'},
                {'label': 'Valor Total Debitado', 'value': f'{total_debitado:,.2f} Kz', 'color': 'danger'},
                {'label': 'Valor Aprovado', 'value': f'{aprovadas:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['ND', 'Cliente', 'Factura', 'Valor', 'Estado', 'Data', 'Motivo'],
            'rows': [
                {
                    'cells': [n.numero_nota, n.cliente.nome, n.factura_relacionada.numero_factura,
                              f'{n.valor:,.2f}', n.estado, n.data.strftime('%d/%m/%Y'), n.motivo[:50]],
                    'url': 'financeiro:nota_debito_detalhe',
                    'pk': n.pk,
                }
                for n in qs.select_related('cliente', 'factura_relacionada')[:200]
            ],
            'filtro_estado': estado,
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
            'estados': ['Pendente', 'Aprovada', 'Rejeitada', 'Cancelada'],
        })
        return context


# ── Relatórios Financeiros ──────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioContasAReceberView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Contas a Receber'
    report_subtitle = 'Facturas pendentes e parcialmente pagas'
    active_sub = 'rel_contas_receber'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope()
        qs = FacturaCliente.objects.filter(
            cliente__in=clientes,
            estado__in=['Pendente', 'Parcialmente Paga']
        )

        total_a_receber = qs.aggregate(t=Sum('valor_total'))['t'] or 0
        total_pago = qs.aggregate(t=Sum('valor_pago'))['t'] or 0
        saldo_pendente = total_a_receber - total_pago

        context.update({
            'summary_cards': [
                {'label': 'Facturas Pendentes', 'value': qs.count(), 'color': 'danger'},
                {'label': 'Valor Total a Receber', 'value': f'{total_a_receber:,.2f} Kz', 'color': 'warning'},
                {'label': 'Saldo Pendente', 'value': f'{saldo_pendente:,.2f} Kz', 'color': 'primary'},
            ],
            'columns': ['Factura', 'Cliente', 'Valor', 'Pago', 'Saldo', 'Vencimento', 'Estado'],
            'rows': [
                {
                    'cells': [f.numero_factura, f.cliente.nome, f'{f.valor_total:,.2f}',
                              f'{f.valor_pago:,.2f}', f'{f.valor_total - f.valor_pago:,.2f}',
                              f.data_vencimento.strftime('%d/%m/%Y'), f.estado],
                    'url': 'financeiro:factura_detalhe',
                    'pk': f.pk,
                }
                for f in qs.select_related('cliente').order_by('data_vencimento')[:200]
            ],
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioClientesDevedoresView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Clientes Devedores'
    report_subtitle = 'Clientes com saldo negativo em conta corrente'
    active_sub = 'rel_clientes_devedores'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope().filter(saldo_conta_corrente__lt=0).order_by('saldo_conta_corrente')

        total_divida = clientes.aggregate(t=Sum('saldo_conta_corrente'))['t'] or 0

        rows = []
        for c in clientes:
            facturas = FacturaCliente.objects.filter(cliente=c, estado__in=['Pendente', 'Parcialmente Paga'])
            total_facturas = facturas.aggregate(t=Sum('valor_total'))['t'] or 0
            rows.append({
                'cells': [
                    c.nome, c.nif, c.telefone or 'N/D',
                    f'{abs(c.saldo_conta_corrente):,.2f}',
                    f'{total_facturas:,.2f}',
                ],
                'url': 'financeiro:conta_corrente_cliente',
                'pk': c.pk,
            })

        context.update({
            'summary_cards': [
                {'label': 'Clientes Devedores', 'value': clientes.count(), 'color': 'danger'},
                {'label': 'Dívida Total', 'value': f'{abs(total_divida):,.2f} Kz', 'color': 'warning'},
            ],
            'columns': ['Cliente', 'NIF', 'Telefone', 'Dívida CC', 'Facturas Pendentes'],
            'rows': rows,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioFluxoCaixaView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Fluxo de Caixa'
    report_subtitle = 'Movimentação financeira por período'
    active_sub = 'rel_fluxo_caixa'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ano = self.request.GET.get('ano', str(timezone.now().year))
        try:
            ano = int(ano)
        except ValueError:
            ano = timezone.now().year

        clientes = self.clientes_scope()
        meses = OrderedDict()
        for m in range(1, 13):
            di = date(ano, m, 1)
            df = date(ano + 1, 1, 1) if m == 12 else date(ano, m + 1, 1)
            entradas = 0
            saidas = 0
            for c in clientes:
                saidas += float(
                    FacturaCliente.objects.filter(cliente=c, data_emissao__date__gte=di, data_emissao__date__lt=df)
                    .exclude(estado='Cancelada')
                    .aggregate(t=Sum('valor_total'))['t'] or 0
                )
                saidas += float(
                    NotaDebito.objects.filter(cliente=c, data__gte=di, data__lt=df, estado='Aprovada')
                    .aggregate(t=Sum('valor'))['t'] or 0
                )
                entradas += float(
                    ReciboCliente.objects.filter(cliente=c, data_pagamento__gte=di, data_pagamento__lt=df)
                    .aggregate(t=Sum('valor_recebido'))['t'] or 0
                )
                entradas += float(
                    FacturaRecibo.objects.filter(cliente=c, data__gte=di, data__lt=df)
                    .exclude(estado='Cancelada')
                    .aggregate(t=Sum('valor'))['t'] or 0
                )
            meses[m] = {'entradas': entradas, 'saidas': saidas, 'saldo': entradas - saidas}

        total_entradas = sum(m['entradas'] for m in meses.values())
        total_saidas = sum(m['saidas'] for m in meses.values())

        meses_pt = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                     'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

        context.update({
            'summary_cards': [
                {'label': 'Total Entradas', 'value': f'{total_entradas:,.2f} Kz', 'color': 'success'},
                {'label': 'Total Saídas', 'value': f'{total_saidas:,.2f} Kz', 'color': 'danger'},
                {'label': 'Saldo Líquido', 'value': f'{total_entradas - total_saidas:,.2f} Kz', 'color': 'primary'},
            ],
            'columns': ['Mês', 'Entradas (Kz)', 'Saídas (Kz)', 'Saldo (Kz)'],
            'rows': [
                {
                    'cells': [
                        meses_pt[m - 1],
                        f'{meses[m]["entradas"]:,.2f}',
                        f'{meses[m]["saidas"]:,.2f}',
                        f'{meses[m]["saldo"]:,.2f}',
                    ],
                    'url': None, 'pk': None,
                }
                for m in range(1, 13)
            ],
            'filtro_ano': str(ano),
            'anos_disponiveis': list(range(2020, timezone.now().year + 2)),
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioDemonstrativoReceitasView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Demonstrativo de Receitas'
    report_subtitle = 'Receitas por tipo de documento'
    active_sub = 'rel_demonstrativo'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        clientes = self.clientes_scope()

        qs_fact = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
        qs_rec = ReciboCliente.objects.filter(cliente__in=clientes)
        qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
        qs_nc = NotaCredito.objects.filter(cliente__in=clientes, estado='Aprovada')
        qs_nd = NotaDebito.objects.filter(cliente__in=clientes, estado='Aprovada')

        if di:
            qs_fact = qs_fact.filter(data_emissao__date__gte=di)
            qs_rec = qs_rec.filter(data_pagamento__gte=di)
            qs_fr = qs_fr.filter(data__gte=di)
            qs_nc = qs_nc.filter(data__gte=di)
            qs_nd = qs_nd.filter(data__gte=di)
        if df:
            qs_fact = qs_fact.filter(data_emissao__date__lte=df)
            qs_rec = qs_rec.filter(data_pagamento__lte=df)
            qs_fr = qs_fr.filter(data__lte=df)
            qs_nc = qs_nc.filter(data__lte=df)
            qs_nd = qs_nd.filter(data__lte=df)

        total_facturas = qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0
        total_recibos = qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0
        total_fr = qs_fr.aggregate(t=Sum('valor'))['t'] or 0
        total_nc = qs_nc.aggregate(t=Sum('valor_creditado'))['t'] or 0
        total_nd = qs_nd.aggregate(t=Sum('valor'))['t'] or 0

        receita_bruta = float(total_facturas) + float(total_fr) + float(total_nd)
        deducoes = float(total_nc)
        receita_liquida = receita_bruta - deducoes
        recebido = float(total_recibos) + float(total_fr)

        context.update({
            'summary_cards': [
                {'label': 'Receita Bruta', 'value': f'{receita_bruta:,.2f} Kz', 'color': 'primary'},
                {'label': 'Receita Líquida', 'value': f'{receita_liquida:,.2f} Kz', 'color': 'success'},
                {'label': 'Total Recebido', 'value': f'{recebido:,.2f} Kz', 'color': 'info'},
            ],
            'columns': ['Tipo', 'Valor (Kz)'],
            'rows': [
                {'cells': ['Facturas Emitidas', f'{total_facturas:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['Facturas-Recibo', f'{total_fr:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['Notas de Débito', f'{total_nd:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['(-) Notas de Crédito', f'({total_nc:,.2f})'], 'url': None, 'pk': None},
                {'cells': ['Receita Líquida', f'{receita_liquida:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['Recebido via Recibos', f'{total_recibos:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['Recebido via F-Recibo', f'{total_fr:,.2f}'], 'url': None, 'pk': None},
            ],
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioBalanceteFinanceiroView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Balancete Financeiro'
    report_subtitle = 'Saldo consolidado de todas as contas'
    active_sub = 'rel_balancete'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope()

        total_saldo_cc = clientes.aggregate(t=Sum('saldo_conta_corrente'))['t'] or 0
        total_facturas = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
            .aggregate(t=Sum('valor_total'))['t'] or 0
        total_pago = FacturaCliente.objects.filter(cliente__in=clientes) \
            .aggregate(t=Sum('valor_pago'))['t'] or 0
        total_recibos = ReciboCliente.objects.filter(cliente__in=clientes) \
            .aggregate(t=Sum('valor_recebido'))['t'] or 0
        total_nc = NotaCredito.objects.filter(cliente__in=clientes, estado='Aprovada') \
            .aggregate(t=Sum('valor_creditado'))['t'] or 0
        total_nd = NotaDebito.objects.filter(cliente__in=clientes, estado='Aprovada') \
            .aggregate(t=Sum('valor'))['t'] or 0
        total_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
            .aggregate(t=Sum('valor'))['t'] or 0
        total_hist_req = RequisicaoFundo.objects.all().filter(cliente__in=clientes, estado='Aprovada') \
            .aggregate(t=Sum('valor_solicitado'))['t'] or 0

        context.update({
            'summary_cards': [
                {'label': 'Saldo CC (Clientes)', 'value': f'{total_saldo_cc:,.2f} Kz', 'color': 'primary'},
                {'label': 'Total Facturado', 'value': f'{total_facturas:,.2f} Kz', 'color': 'warning'},
                {'label': 'Total Recebido', 'value': f'{total_recibos + total_fr:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['Conta', 'Valor (Kz)', 'Tipo'],
            'rows': [
                {'cells': ['Saldo Conta Corrente (Clientes)', f'{total_saldo_cc:,.2f}', 'Passivo'],
                 'url': None, 'pk': None},
                {'cells': ['Facturas Emitidas (não canceladas)', f'{total_facturas:,.2f}', 'Activo'],
                 'url': None, 'pk': None},
                {'cells': ['Valor Pago (Facturas)', f'{total_pago:,.2f}', 'Activo'],
                 'url': None, 'pk': None},
                {'cells': ['Recibos Emitidos', f'{total_recibos:,.2f}', 'Activo'],
                 'url': None, 'pk': None},
                {'cells': ['Notas de Crédito Aprovadas', f'{total_nc:,.2f}', 'Passivo'],
                 'url': None, 'pk': None},
                {'cells': ['Notas de Débito Aprovadas', f'{total_nd:,.2f}', 'Activo'],
                 'url': None, 'pk': None},
                {'cells': ['Facturas-Recibo', f'{total_fr:,.2f}', 'Activo'],
                 'url': None, 'pk': None},
                {'cells': ['Requisições Aprovadas', f'{total_hist_req:,.2f}', 'Passivo'],
                 'url': None, 'pk': None},
            ],
        })
        return context


# ── Relatórios Executivos ──────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioDashboardFinanceiroView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_dashboard.html'
    report_name = 'Dashboard Financeiro'
    report_subtitle = 'Painel executivo com indicadores financeiros'
    active_sub = 'rel_dashboard'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope()

        qs_fact = FacturaCliente.objects.filter(cliente__in=clientes)
        tot_fact = qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0
        tot_pago = qs_fact.aggregate(t=Sum('valor_pago'))['t'] or 0
        saldo_cc = clientes.aggregate(t=Sum('saldo_conta_corrente'))['t'] or 0

        qs_rec = ReciboCliente.objects.filter(cliente__in=clientes)
        tot_rec = qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0

        qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
        tot_fr = qs_fr.aggregate(t=Sum('valor'))['t'] or 0

        margem = min((float(tot_rec) + float(tot_fr)) / float(tot_fact) * 100, 100) if tot_fact else 0
        clientes_com_divida = clientes.filter(saldo_conta_corrente__lt=0).count()
        total_clientes = clientes.count()
        pct_inadimplencia = (clientes_com_divida / total_clientes * 100) if total_clientes else 0

        context.update({
            'total_facturado': f'{tot_fact:,.2f}',
            'total_recebido': f'{float(tot_rec) + float(tot_fr):,.2f}',
            'saldo_cc': f'{saldo_cc:,.2f}',
            'margem_recebimento': f'{margem:.1f}',
            'clientes_com_divida': clientes_com_divida,
            'total_clientes': total_clientes,
            'taxa_inadimplencia': f'{pct_inadimplencia:.1f}',
            'total_facturas_pagas': qs_fact.filter(estado='Paga').count(),
            'total_facturas_pendentes': qs_fact.filter(estado__in=['Pendente', 'Parcialmente Paga']).count(),
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioIndicadoresCobrancaView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Indicadores de Cobrança'
    report_subtitle = 'Eficiência na cobrança e recebimento'
    active_sub = 'rel_indicadores'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope()

        qs_fact = FacturaCliente.objects.filter(cliente__in=clientes)
        qs_rec = ReciboCliente.objects.filter(cliente__in=clientes)
        qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')

        total_facturado = float(qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0)
        total_pago = float(qs_fact.aggregate(t=Sum('valor_pago'))['t'] or 0)
        total_recebido = float(qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0) + \
                         float(qs_fr.aggregate(t=Sum('valor'))['t'] or 0)

        prazo_medio = 0
        tem_prazo = False
        if qs_rec.count() > 0:
            dias, contados = 0, 0
            for r in qs_rec[:100]:
                if r.data_pagamento and r.data_criacao:
                    dias += (r.data_pagamento - r.data_criacao.date()).days
                    contados += 1
            if contados:
                prazo_medio = dias / contados
                tem_prazo = True

        eficiencia = min(total_recebido / total_facturado * 100, 100) if total_facturado else 0
        taxa_pagamento = min(total_pago / total_facturado * 100, 100) if total_facturado else 0
        devedores = clientes.filter(saldo_conta_corrente__lt=0).count()
        total_clientes = clientes.count()
        inadimplencia = (devedores / total_clientes * 100) if total_clientes else 0

        prazo_label = f'{prazo_medio:.0f} dias' if tem_prazo else '—'

        context.update({
            'summary_cards': [
                {'label': 'Eficiência de Cobrança', 'value': f'{eficiencia:.1f}%', 'color': 'success'},
                {'label': 'Prazo Médio Recebimento', 'value': prazo_label, 'color': 'primary'},
                {'label': 'Taxa de Inadimplência', 'value': f'{inadimplencia:.1f}%', 'color': 'danger'},
            ],
            'columns': ['Indicador', 'Valor'],
            'rows': [
                {'cells': ['Eficiência de Cobrança', f'{eficiencia:.1f}%'], 'url': None, 'pk': None},
                {'cells': ['Prazo Médio de Recebimento', prazo_label], 'url': None, 'pk': None},
                {'cells': ['Taxa de Pagamento (valor pago / facturado)', f'{taxa_pagamento:.1f}%'],
                 'url': None, 'pk': None},
                {'cells': ['Clientes em Dívida', str(devedores)], 'url': None, 'pk': None},
                {'cells': ['Taxa de Inadimplência', f'{inadimplencia:.1f}%'], 'url': None, 'pk': None},
                {'cells': ['Total Recebido (Kz)', f'{total_recebido:,.2f}'], 'url': None, 'pk': None},
                {'cells': ['Total Facturado (Kz)', f'{total_facturado:,.2f}'], 'url': None, 'pk': None},
            ],
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioReceitaPorClienteView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Receita por Cliente'
    report_subtitle = 'Facturação e recebimentos agrupados por cliente'
    active_sub = 'rel_receita_cliente'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        di, df, data_ini, data_fim = self.parse_dates()
        clientes = self.clientes_scope().filter(ativo=True)

        rows = []
        total_geral_receita = 0
        for c in clientes:
            qs_f = FacturaCliente.objects.filter(cliente=c).exclude(estado='Cancelada')
            qs_r = ReciboCliente.objects.filter(cliente=c)
            qs_fr = FacturaRecibo.objects.filter(cliente=c).exclude(estado='Cancelada')
            if di:
                qs_f = qs_f.filter(data_emissao__date__gte=di)
                qs_r = qs_r.filter(data_pagamento__gte=di)
                qs_fr = qs_fr.filter(data__gte=di)
            if df:
                qs_f = qs_f.filter(data_emissao__date__lte=df)
                qs_r = qs_r.filter(data_pagamento__lte=df)
                qs_fr = qs_fr.filter(data__lte=df)

            total_f = float(qs_f.aggregate(t=Sum('valor_total'))['t'] or 0)
            total_r = float(qs_r.aggregate(t=Sum('valor_recebido'))['t'] or 0)
            total_fr = float(qs_fr.aggregate(t=Sum('valor'))['t'] or 0)
            receita_total = total_f + total_fr
            total_geral_receita += receita_total
            rows.append({
                'cells': [c.nome, c.nif, f'{total_f:,.2f}', f'{total_fr:,.2f}',
                          f'{total_r:,.2f}', f'{receita_total:,.2f}'],
                'url': 'financeiro:conta_corrente_cliente',
                'pk': c.pk,
            })

        rows.sort(key=lambda r: float(r['cells'][5].replace(',', '')), reverse=True)

        context.update({
            'summary_cards': [
                {'label': 'Total de Clientes', 'value': len(rows), 'color': 'primary'},
                {'label': 'Receita Total', 'value': f'{total_geral_receita:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['Cliente', 'NIF', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
            'rows': rows,
            'filtro_data_ini': data_ini,
            'filtro_data_fim': data_fim,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioReceitaPorLocalizacaoView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Receita por Localização'
    report_subtitle = 'Facturação agrupada por localização do cliente'
    active_sub = 'rel_receita_localizacao'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clientes = self.clientes_scope().filter(ativo=True)

        from collections import defaultdict
        dados = defaultdict(lambda: {'clientes': 0, 'facturado': 0, 'recebido': 0, 'fr': 0})
        for c in clientes:
            loc = c.localizacao.strip()[:30] if c.localizacao else 'Não definida'
            dados[loc]['clientes'] += 1
            dados[loc]['facturado'] += float(
                FacturaCliente.objects.filter(cliente=c).exclude(estado='Cancelada')
                .aggregate(t=Sum('valor_total'))['t'] or 0
            )
            dados[loc]['recebido'] += float(
                ReciboCliente.objects.filter(cliente=c)
                .aggregate(t=Sum('valor_recebido'))['t'] or 0
            )
            dados[loc]['fr'] += float(
                FacturaRecibo.objects.filter(cliente=c).exclude(estado='Cancelada')
                .aggregate(t=Sum('valor'))['t'] or 0
            )

        total_geral = sum(d['facturado'] + d['fr'] for d in dados.values())
        rows = [
            {
                'cells': [
                    loc,
                    str(info['clientes']),
                    f'{info["facturado"]:,.2f}',
                    f'{info["fr"]:,.2f}',
                    f'{info["recebido"]:,.2f}',
                    f'{info["facturado"] + info["fr"]:,.2f}',
                ],
                'url': None, 'pk': None,
            }
            for loc, info in sorted(dados.items(), key=lambda x: x[1]['facturado'] + x[1]['fr'], reverse=True)
        ]

        context.update({
            'summary_cards': [
                {'label': 'Localizações', 'value': len(dados), 'color': 'primary'},
                {'label': 'Receita Total', 'value': f'{total_geral:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['Localização', 'Clientes', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
            'rows': rows,
        })
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RelatorioReceitaPorDespachanteView(ReportMixin, TemplateView):
    allowed_roles = ['Gestor Financeiro', 'Administrador']
    template_name = 'financeiro/relatorio_financeiro.html'
    report_name = 'Receita por Despachante'
    report_subtitle = 'Facturação e recebimentos agrupados por despachante'
    active_sub = 'rel_receita_despachante'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        despachantes = Usuario.objects.filter(status='Ativo', papel__in=['Despachante Oficial', 'Administrador'])
        clientes = self.clientes_scope()

        rows = []
        total_geral = 0
        for d in despachantes:
            cls = clientes.filter(usuario_id=d.pk)
            if not cls.exists():
                continue
            total_f = float(
                FacturaCliente.objects.filter(cliente__in=cls).exclude(estado='Cancelada')
                .aggregate(t=Sum('valor_total'))['t'] or 0
            )
            total_r = float(
                ReciboCliente.objects.filter(cliente__in=cls)
                .aggregate(t=Sum('valor_recebido'))['t'] or 0
            )
            total_fr = float(
                FacturaRecibo.objects.filter(cliente__in=cls).exclude(estado='Cancelada')
                .aggregate(t=Sum('valor'))['t'] or 0
            )
            receita = total_f + total_fr
            total_geral += receita
            rows.append({
                'cells': [d.nome, d.papel, str(cls.count()), f'{total_f:,.2f}',
                          f'{total_fr:,.2f}', f'{total_r:,.2f}', f'{receita:,.2f}'],
                'url': None, 'pk': None,
            })

        rows.sort(key=lambda r: float(r['cells'][6].replace(',', '')), reverse=True)

        context.update({
            'summary_cards': [
                {'label': 'Despachantes', 'value': len(rows), 'color': 'primary'},
                {'label': 'Receita Total', 'value': f'{total_geral:,.2f} Kz', 'color': 'success'},
            ],
            'columns': ['Despachante', 'Perfil', 'Clientes', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
            'rows': rows,
        })
        return context
