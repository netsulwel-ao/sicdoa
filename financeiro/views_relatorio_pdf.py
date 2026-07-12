"""
Views de PDF para relatórios financeiros.
Gera PDFs profissionais seguindo o padrão da Requisição de Fundos (CDOA).
"""
import logging
from collections import OrderedDict, defaultdict
from datetime import datetime
from decimal import Decimal

from django.http import HttpResponse
from django.db.models import Sum, OuterRef, Subquery
from django.db.models.functions import ExtractMonth
from django.utils import timezone

from users.auth_decorators import requer_sessao_ativa
from users.permissoes import get_usuario_permissoes
from clientes.models import Cliente
from .models import (
    FacturaCliente, ReciboCliente, NotaCredito, NotaDebito,
    FacturaRecibo, RequisicaoFundo,
)
from .views import _user_tem_acesso_total, _tem_escopo_filial
from .pdf_utils import gerar_pdf_relatorio
from utils.format_kz import fmt_kz

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _get_user_filter(request):
    if _user_tem_acesso_total(request):
        return {}
    banca_id = request.session.get('banca_id')
    if not banca_id:
        usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
        if usuario_id:
            return {'usuario_id': usuario_id}
    else:
        filtro = {'banca_id': banca_id}
        filial_id = request.session.get('colaborador_filial_id')
        if filial_id:
            perm_set = get_usuario_permissoes(request)
            if _tem_escopo_filial(perm_set, filial_id):
                filtro['filial_id'] = filial_id
        return filtro
    return {}


def _get_banca(request):
    from rh.models import Banca
    banca_id = request.session.get('banca_id')
    if banca_id:
        return Banca.objects.filter(pk=banca_id).first()
    usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
    if usuario_id:
        return Banca.objects.filter(usuario_id=usuario_id).first()
    return None


def _parse_dates(request):
    data_ini = request.GET.get('data_ini', '')
    data_fim = request.GET.get('data_fim', '')
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


def _montar_periodo(data_ini, data_fim):
    partes = []
    if data_ini:
        partes.append(f"De {data_ini.strftime('%d/%m/%Y')}")
    if data_fim:
        partes.append(f"Ate {data_fim.strftime('%d/%m/%Y')}")
    return ' '.join(partes) if partes else 'Todos os periodos'


# ── Dados por tipo de relatorio ─────────────────────────────────────────────

def _dados_facturacao(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    qs = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    if di:
        qs = qs.filter(data_emissao__date__gte=di)
    if df:
        qs = qs.filter(data_emissao__date__lte=df)

    total_facturado = qs.aggregate(t=Sum('valor_total'))['t'] or 0
    total_pago = qs.aggregate(t=Sum('valor_pago'))['t'] or 0
    pendentes = qs.filter(estado__in=['Pendente', 'Parcialmente Paga']).count()

    return {
        'report_name': 'Relatorio de Facturacao',
        'report_subtitle': 'Resumo de todas as facturas emitidas',
        'summary_cards': [
            {'label': 'Total Facturado', 'value': f'{fmt_kz(total_facturado)} Kz', 'color': 'primary'},
            {'label': 'Total Pago', 'value': f'{fmt_kz(total_pago)} Kz', 'color': 'success'},
            {'label': 'Facturas Pendentes', 'value': str(pendentes), 'color': 'danger'},
        ],
        'columns': ['Factura', 'Cliente', 'Valor Total', 'Valor Pago', 'Estado', 'Emissao'],
        'rows': [
            {'cells': [f.numero_factura, f.cliente.nome if f.cliente else 'N/D',
                       f'{fmt_kz(f.valor_total)}', f'{fmt_kz(f.valor_pago)}',
                       f.estado, f.data_emissao.strftime('%d/%m/%Y')]}
            for f in qs.select_related('cliente')[:200]
        ],
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim)},
    }


def _dados_recibos(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    fp = request.GET.get('forma_pagamento', '')
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    qs = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
    if di:
        qs = qs.filter(data_pagamento__gte=di)
    if df:
        qs = qs.filter(data_pagamento__lte=df)
    if fp:
        qs = qs.filter(forma_pagamento=fp)

    total_recebido = qs.aggregate(t=Sum('valor_recebido'))['t'] or 0
    por_forma = qs.values('forma_pagamento').annotate(total=Sum('valor_recebido')).order_by('-total')

    extra = []
    if por_forma.exists():
        extra.append({
            'title': 'Recebimentos por Forma de Pagamento',
            'columns': ['Forma de Pagamento', 'Total'],
            'rows': [{'cells': [p['forma_pagamento'], f"{fmt_kz(p['total'])} Kz"]} for p in por_forma],
        })

    return {
        'report_name': 'Relatorio de Recibos',
        'report_subtitle': 'Resumo de todos os recebimentos',
        'summary_cards': [
            {'label': 'Total de Recibos', 'value': str(qs.count()), 'color': 'primary'},
            {'label': 'Valor Total Recebido', 'value': f'{fmt_kz(total_recebido)} Kz', 'color': 'success'},
            {'label': 'Formas de Pagamento', 'value': str(por_forma.count()), 'color': 'primary'},
        ],
        'columns': ['Recibo', 'Cliente', 'Valor', 'Forma Pagamento', 'Data', 'Responsavel'],
        'rows': [
            {'cells': [r.numero_recibo, r.cliente.nome if r.cliente else 'N/D',
                       f'{fmt_kz(r.valor_recebido)}', r.forma_pagamento,
                       r.data_pagamento.strftime('%d/%m/%Y'), r.utilizador_responsavel_nome]}
            for r in qs.select_related('cliente')[:200]
        ],
        'extra_tables': extra,
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim), 'Forma Pagamento': fp or 'Todas'},
    }


def _dados_requisicoes_fundos(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    estado = request.GET.get('estado', '')
    filtro = _get_user_filter(request)
    qs = RequisicaoFundo.objects.all()
    if filtro:
        qs = qs.filter(**filtro)
    if di:
        qs = qs.filter(data_emissao__date__gte=di)
    if df:
        qs = qs.filter(data_emissao__date__lte=df)
    if estado:
        qs = qs.filter(estado=estado)

    return {
        'report_name': 'Relatorio de Requisicao de Fundos',
        'report_subtitle': 'Listagem de todas as requisicoes de fundos',
        'summary_cards': [
            {'label': 'Total de Requisicoes', 'value': str(qs.count()), 'color': 'primary'},
            {'label': 'Estado Pendente', 'value': str(qs.filter(estado='Pendente').count()), 'color': 'warning'},
            {'label': 'Estado Aceite', 'value': str(qs.filter(estado='Aceite').count()), 'color': 'success'},
        ],
        'columns': ['No', 'Cliente', 'Estado', 'Data', 'Criador'],
        'rows': [
            {'cells': [r.numero_requisicao, r.cliente.nome if r.cliente else 'N/D',
                       r.estado, r.data_emissao.strftime('%d/%m/%Y'), r.criado_por_nome]}
            for r in qs.select_related('cliente')[:200]
        ],
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim), 'Estado': estado or 'Todos'},
    }


def _dados_notas_credito(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    estado = request.GET.get('estado', '')
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    qs = NotaCredito.objects.filter(cliente__in=clientes)
    if di:
        qs = qs.filter(data__gte=di)
    if df:
        qs = qs.filter(data__lte=df)
    if estado:
        qs = qs.filter(estado=estado)

    total_creditado = qs.aggregate(t=Sum('valor_creditado'))['t'] or 0
    aprovadas = qs.filter(estado='Aprovada').aggregate(t=Sum('valor_creditado'))['t'] or 0

    return {
        'report_name': 'Relatorio de Notas de Credito',
        'report_subtitle': 'Resumo de todas as notas de credito emitidas',
        'summary_cards': [
            {'label': 'Total de NC', 'value': str(qs.count()), 'color': 'primary'},
            {'label': 'Valor Total Creditado', 'value': f'{fmt_kz(total_creditado)} Kz', 'color': 'warning'},
            {'label': 'Valor Aprovado', 'value': f'{fmt_kz(aprovadas)} Kz', 'color': 'success'},
        ],
        'columns': ['NC', 'Cliente', 'Factura', 'Valor', 'Estado', 'Data', 'Motivo'],
        'rows': [
            {'cells': [n.numero_nota, n.cliente.nome if n.cliente else 'N/D',
                       n.factura_relacionada.numero_factura if n.factura_relacionada else 'N/D',
                       f'{fmt_kz(n.valor_creditado)}', n.estado,
                       n.data.strftime('%d/%m/%Y'), (n.motivo or '')[:50]]}
            for n in qs.select_related('cliente', 'factura_relacionada')[:200]
        ],
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim), 'Estado': estado or 'Todos'},
    }


def _dados_notas_debito(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    estado = request.GET.get('estado', '')
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    qs = NotaDebito.objects.filter(cliente__in=clientes)
    if di:
        qs = qs.filter(data__gte=di)
    if df:
        qs = qs.filter(data__lte=df)
    if estado:
        qs = qs.filter(estado=estado)

    total_debitado = qs.aggregate(t=Sum('valor'))['t'] or 0
    aprovadas = qs.filter(estado='Aprovada').aggregate(t=Sum('valor'))['t'] or 0

    return {
        'report_name': 'Relatorio de Notas de Debito',
        'report_subtitle': 'Resumo de todas as notas de debito emitidas',
        'summary_cards': [
            {'label': 'Total de ND', 'value': str(qs.count()), 'color': 'primary'},
            {'label': 'Valor Total Debitado', 'value': f'{fmt_kz(total_debitado)} Kz', 'color': 'danger'},
            {'label': 'Valor Aprovado', 'value': f'{fmt_kz(aprovadas)} Kz', 'color': 'success'},
        ],
        'columns': ['ND', 'Cliente', 'Factura', 'Valor', 'Estado', 'Data', 'Motivo'],
        'rows': [
            {'cells': [n.numero_nota, n.cliente.nome if n.cliente else 'N/D',
                       n.factura_relacionada.numero_factura if n.factura_relacionada else 'N/D',
                       f'{fmt_kz(n.valor)}', n.estado,
                       n.data.strftime('%d/%m/%Y'), (n.motivo or '')[:50]]}
            for n in qs.select_related('cliente', 'factura_relacionada')[:200]
        ],
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim), 'Estado': estado or 'Todos'},
    }


def _dados_contas_receber(request):
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    qs = FacturaCliente.objects.filter(cliente__in=clientes, estado__in=['Pendente', 'Parcialmente Paga'])
    total_a_receber = qs.aggregate(t=Sum('valor_total'))['t'] or 0
    total_pago = qs.aggregate(t=Sum('valor_pago'))['t'] or 0
    saldo_pendente = total_a_receber - total_pago

    return {
        'report_name': 'Contas a Receber',
        'report_subtitle': 'Facturas pendentes e parcialmente pagas',
        'summary_cards': [
            {'label': 'Facturas Pendentes', 'value': str(qs.count()), 'color': 'danger'},
            {'label': 'Valor Total a Receber', 'value': f'{fmt_kz(total_a_receber)} Kz', 'color': 'warning'},
            {'label': 'Saldo Pendente', 'value': f'{fmt_kz(saldo_pendente)} Kz', 'color': 'primary'},
        ],
        'columns': ['Factura', 'Cliente', 'Valor', 'Pago', 'Saldo', 'Vencimento', 'Estado'],
        'rows': [
            {'cells': [f.numero_factura, f.cliente.nome if f.cliente else 'N/D',
                       f'{fmt_kz(f.valor_total)}', f'{fmt_kz(f.valor_pago)}',
                       f'{fmt_kz(f.valor_total - f.valor_pago)}',
                       f.data_vencimento.strftime('%d/%m/%Y'), f.estado]}
            for f in qs.select_related('cliente').order_by('data_vencimento')[:200]
        ],
        'filtros': {'Estado': 'Pendente / Parcialmente Paga'},
    }


def _dados_clientes_devedores(request):
    filtro = _get_user_filter(request)
    base = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    clientes = base.filter(saldo_conta_corrente__lt=0).order_by('saldo_conta_corrente')
    total_divida = clientes.aggregate(t=Sum('saldo_conta_corrente'))['t'] or 0

    subq = FacturaCliente.objects.filter(
        cliente=OuterRef('pk'), estado__in=['Pendente', 'Parcialmente Paga']
    ).values('cliente').annotate(t=Sum('valor_total')).values('t')[:1]
    clientes = clientes.annotate(total_facturas=Subquery(subq))

    rows = [
        {'cells': [c.nome, c.nif, c.telefone or 'N/D',
                   f'{fmt_kz(abs(c.saldo_conta_corrente))}',
                   f'{fmt_kz(c.total_facturas or 0)}']}
        for c in clientes
    ]

    return {
        'report_name': 'Clientes Devedores',
        'report_subtitle': 'Clientes com saldo negativo em conta corrente',
        'summary_cards': [
            {'label': 'Clientes Devedores', 'value': str(clientes.count()), 'color': 'danger'},
            {'label': 'Divida Total', 'value': f'{fmt_kz(abs(total_divida))} Kz', 'color': 'warning'},
        ],
        'columns': ['Cliente', 'NIF', 'Telefone', 'Divida CC', 'Facturas Pendentes'],
        'rows': rows,
        'filtros': {'Estado': 'Saldo negativo'},
    }


def _dados_fluxo_caixa(request):
    ano = request.GET.get('ano', str(timezone.now().year))
    try:
        ano = int(ano)
    except ValueError:
        ano = timezone.now().year

    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()

    meses_pt = ['Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

    facturas = FacturaCliente.objects.filter(cliente__in=clientes, data_emissao__year=ano) \
        .exclude(estado='Cancelada').annotate(mes=ExtractMonth('data_emissao')) \
        .values('mes').annotate(total=Sum('valor_total'))
    notas_debito = NotaDebito.objects.filter(cliente__in=clientes, data__year=ano, estado='Aprovada') \
        .annotate(mes=ExtractMonth('data')).values('mes').annotate(total=Sum('valor'))
    recibos = ReciboCliente.objects.filter(cliente__in=clientes, data_pagamento__year=ano) \
        .exclude(estado='Cancelado').annotate(mes=ExtractMonth('data_pagamento')) \
        .values('mes').annotate(total=Sum('valor_recebido'))
    facturas_recibo = FacturaRecibo.objects.filter(cliente__in=clientes, data__year=ano) \
        .exclude(estado='Cancelada').annotate(mes=ExtractMonth('data')) \
        .values('mes').annotate(total=Sum('valor'))

    saidas_map = {}
    for r in facturas:
        saidas_map[r['mes']] = saidas_map.get(r['mes'], 0) + float(r['total'])
    for r in notas_debito:
        saidas_map[r['mes']] = saidas_map.get(r['mes'], 0) + float(r['total'])
    entradas_map = {}
    for r in recibos:
        entradas_map[r['mes']] = entradas_map.get(r['mes'], 0) + float(r['total'])
    for r in facturas_recibo:
        entradas_map[r['mes']] = entradas_map.get(r['mes'], 0) + float(r['total'])

    meses_data = OrderedDict()
    for m in range(1, 13):
        e = entradas_map.get(m, 0)
        s = saidas_map.get(m, 0)
        meses_data[m] = {'entradas': e, 'saidas': s, 'saldo': e - s}

    total_entradas = sum(m['entradas'] for m in meses_data.values())
    total_saidas = sum(m['saidas'] for m in meses_data.values())

    return {
        'report_name': 'Fluxo de Caixa',
        'report_subtitle': f'Movimentacao financeira - {ano}',
        'summary_cards': [
            {'label': 'Total Entradas', 'value': f'{fmt_kz(total_entradas)} Kz', 'color': 'success'},
            {'label': 'Total Saidas', 'value': f'{fmt_kz(total_saidas)} Kz', 'color': 'danger'},
            {'label': 'Saldo Liquido', 'value': f'{fmt_kz(total_entradas - total_saidas)} Kz', 'color': 'primary'},
        ],
        'columns': ['Mes', 'Entradas (Kz)', 'Saidas (Kz)', 'Saldo (Kz)'],
        'rows': [
            {'cells': [meses_pt[m - 1], f'{fmt_kz(meses_data[m]["entradas"])}',
                       f'{fmt_kz(meses_data[m]["saidas"])}', f'{fmt_kz(meses_data[m]["saldo"])}']}
            for m in range(1, 13)
        ],
        'filtros': {'Ano': str(ano)},
    }


def _dados_demonstrativo_receitas(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()

    qs_fact = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    qs_rec = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
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

    t_fact = qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0
    t_rec = qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0
    t_fr = qs_fr.aggregate(t=Sum('valor'))['t'] or 0
    t_nc = qs_nc.aggregate(t=Sum('valor_creditado'))['t'] or 0
    t_nd = qs_nd.aggregate(t=Sum('valor'))['t'] or 0

    receita_bruta = float(t_fact) + float(t_fr) + float(t_nd)
    receita_liquida = receita_bruta - float(t_nc)
    recebido = float(t_rec) + float(t_fr)

    return {
        'report_name': 'Demonstrativo de Receitas',
        'report_subtitle': 'Receitas por tipo de documento',
        'summary_cards': [
            {'label': 'Receita Bruta', 'value': f'{fmt_kz(receita_bruta)} Kz', 'color': 'primary'},
            {'label': 'Receita Liquida', 'value': f'{fmt_kz(receita_liquida)} Kz', 'color': 'success'},
            {'label': 'Total Recebido', 'value': f'{fmt_kz(recebido)} Kz', 'color': 'primary'},
        ],
        'columns': ['Tipo', 'Valor (Kz)'],
        'rows': [
            {'cells': ['Facturas Emitidas', f'{fmt_kz(t_fact)}']},
            {'cells': ['Facturas-Recibo', f'{fmt_kz(t_fr)}']},
            {'cells': ['Notas de Debito', f'{fmt_kz(t_nd)}']},
            {'cells': ['(-) Notas de Credito', f'({fmt_kz(t_nc)})']},
            {'cells': ['Receita Liquida', f'{fmt_kz(receita_liquida)}']},
            {'cells': ['Recebido via Recibos', f'{fmt_kz(t_rec)}']},
            {'cells': ['Recebido via F-Recibo', f'{fmt_kz(t_fr)}']},
        ],
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim)},
    }


def _dados_balancete(request):
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()

    total_saldo_cc = clientes.aggregate(t=Sum('saldo_conta_corrente'))['t'] or 0
    total_facturas = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
        .aggregate(t=Sum('valor_total'))['t'] or 0
    total_pago = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
        .aggregate(t=Sum('valor_pago'))['t'] or 0
    total_recibos = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado') \
        .aggregate(t=Sum('valor_recebido'))['t'] or 0
    total_nc = NotaCredito.objects.filter(cliente__in=clientes, estado='Aprovada') \
        .aggregate(t=Sum('valor_creditado'))['t'] or 0
    total_nd = NotaDebito.objects.filter(cliente__in=clientes, estado='Aprovada') \
        .aggregate(t=Sum('valor'))['t'] or 0
    total_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
        .aggregate(t=Sum('valor'))['t'] or 0
    total_req = RequisicaoFundo.objects.filter(cliente__in=clientes, estado='Aprovada') \
        .aggregate(t=Sum('valor_solicitado'))['t'] or 0

    return {
        'report_name': 'Balancete Financeiro',
        'report_subtitle': 'Saldo consolidado de todas as contas',
        'summary_cards': [
            {'label': 'Saldo CC (Clientes)', 'value': f'{fmt_kz(total_saldo_cc)} Kz', 'color': 'primary'},
            {'label': 'Total Facturado', 'value': f'{fmt_kz(total_facturas)} Kz', 'color': 'warning'},
            {'label': 'Total Recebido', 'value': f'{fmt_kz(total_recibos + total_fr)} Kz', 'color': 'success'},
        ],
        'columns': ['Conta', 'Valor (Kz)', 'Tipo'],
        'rows': [
            {'cells': ['Saldo Conta Corrente (Clientes)', f'{fmt_kz(total_saldo_cc)}', 'Passivo']},
            {'cells': ['Facturas Emitidas (nao canceladas)', f'{fmt_kz(total_facturas)}', 'Activo']},
            {'cells': ['Valor Pago (Facturas)', f'{fmt_kz(total_pago)}', 'Activo']},
            {'cells': ['Recibos Emitidos', f'{fmt_kz(total_recibos)}', 'Activo']},
            {'cells': ['Notas de Credito Aprovadas', f'{fmt_kz(total_nc)}', 'Passivo']},
            {'cells': ['Notas de Debito Aprovadas', f'{fmt_kz(total_nd)}', 'Activo']},
            {'cells': ['Facturas-Recibo', f'{fmt_kz(total_fr)}', 'Activo']},
            {'cells': ['Requisicoes Aprovadas', f'{fmt_kz(total_req)}', 'Passivo']},
        ],
        'filtros': {'Tipo': 'Consolidado'},
    }


def _dados_indicadores_cobranca(request):
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()

    qs_fact = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    qs_rec = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
    qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')

    total_facturado = float(qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0)
    total_pago = float(qs_fact.aggregate(t=Sum('valor_pago'))['t'] or 0)
    total_recebido = float(qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0) + \
                     float(qs_fr.aggregate(t=Sum('valor'))['t'] or 0)
    total_fr_standalone = float(qs_fr.filter(factura__isnull=True).aggregate(t=Sum('valor'))['t'] or 0)
    tot_fact_total = total_facturado + total_fr_standalone

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

    eficiencia = (total_recebido / tot_fact_total * 100) if tot_fact_total else 0
    taxa_pagamento = (total_pago / tot_fact_total * 100) if tot_fact_total else 0
    devedores = clientes.filter(saldo_conta_corrente__lt=0).count()
    total_clientes = clientes.count()
    inadimplencia = (devedores / total_clientes * 100) if total_clientes else 0
    prazo_label = f'{prazo_medio:.0f} dias' if tem_prazo else '---'

    return {
        'report_name': 'Indicadores de Cobranca',
        'report_subtitle': 'Eficiencia na cobranca e recebimento',
        'summary_cards': [
            {'label': 'Eficiencia de Cobranca', 'value': f'{eficiencia:.1f}%', 'color': 'success'},
            {'label': 'Prazo Medio Recebimento', 'value': prazo_label, 'color': 'primary'},
            {'label': 'Taxa de Inadimplencia', 'value': f'{inadimplencia:.1f}%', 'color': 'danger'},
        ],
        'columns': ['Indicador', 'Valor'],
        'rows': [
            {'cells': ['Eficiencia de Cobranca', f'{eficiencia:.1f}%']},
            {'cells': ['Prazo Medio de Recebimento', prazo_label]},
            {'cells': ['Taxa de Pagamento (valor pago / facturado)', f'{taxa_pagamento:.1f}%']},
            {'cells': ['Clientes em Divida', str(devedores)]},
            {'cells': ['Taxa de Inadimplencia', f'{inadimplencia:.1f}%']},
            {'cells': ['Total Recebido (Kz)', f'{fmt_kz(total_recebido)}']},
            {'cells': ['Total Facturado (Kz)', f'{fmt_kz(tot_fact_total)}']},
        ],
        'filtros': {},
    }


def _dados_receita_cliente(request):
    di, df, data_ini, data_fim = _parse_dates(request)
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro).filter(ativo=True) if filtro else Cliente.objects.filter(ativo=True)

    qs_f = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    qs_r = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
    qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    if di:
        qs_f = qs_f.filter(data_emissao__date__gte=di)
        qs_r = qs_r.filter(data_pagamento__gte=di)
        qs_fr = qs_fr.filter(data__gte=di)
    if df:
        qs_f = qs_f.filter(data_emissao__date__lte=df)
        qs_r = qs_r.filter(data_pagamento__lte=df)
        qs_fr = qs_fr.filter(data__lte=df)

    facturas_by = {r['cliente_id']: float(r['total']) for r in qs_f.values('cliente_id').annotate(total=Sum('valor_total'))}
    recibos_by = {r['cliente_id']: float(r['total']) for r in qs_r.values('cliente_id').annotate(total=Sum('valor_recebido'))}
    fr_by = {r['cliente_id']: float(r['total']) for r in qs_fr.values('cliente_id').annotate(total=Sum('valor'))}

    rows = []
    total_geral = 0
    for c in clientes:
        tf = facturas_by.get(c.pk, 0)
        tr = recibos_by.get(c.pk, 0)
        tfr = fr_by.get(c.pk, 0)
        receita = tf + tfr
        total_geral += receita
        rows.append({
            'cells': [c.nome, c.nif, f'{fmt_kz(tf)}', f'{fmt_kz(tfr)}', f'{fmt_kz(tr)}', f'{fmt_kz(receita)}'],
            'sort_value': receita,
        })
    rows.sort(key=lambda r: r.get('sort_value', 0), reverse=True)

    return {
        'report_name': 'Receita por Cliente',
        'report_subtitle': 'Facturacao e recebimentos agrupados por cliente',
        'summary_cards': [
            {'label': 'Total de Clientes', 'value': str(len(rows)), 'color': 'primary'},
            {'label': 'Receita Total', 'value': f'{fmt_kz(total_geral)} Kz', 'color': 'success'},
        ],
        'columns': ['Cliente', 'NIF', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
        'rows': rows,
        'filtros': {'Periodo': _montar_periodo(data_ini, data_fim)},
    }


def _dados_receita_localizacao(request):
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro).filter(ativo=True) if filtro else Cliente.objects.filter(ativo=True)

    dados = defaultdict(lambda: {'clientes': 0, 'facturado': 0, 'recebido': 0, 'fr': 0})
    for c in clientes:
        loc = (c.localizacao or 'Nao definida').strip()[:30]
        dados[loc]['clientes'] += 1

    for r in FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
            .values('cliente__localizacao').annotate(total=Sum('valor_total')):
        loc = (r['cliente__localizacao'] or 'Nao definida').strip()[:30]
        dados[loc]['facturado'] += float(r['total'])

    for r in ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado') \
            .values('cliente__localizacao').annotate(total=Sum('valor_recebido')):
        loc = (r['cliente__localizacao'] or 'Nao definida').strip()[:30]
        dados[loc]['recebido'] += float(r['total'])

    for r in FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada') \
            .values('cliente__localizacao').annotate(total=Sum('valor')):
        loc = (r['cliente__localizacao'] or 'Nao definida').strip()[:30]
        dados[loc]['fr'] += float(r['total'])

    total_geral = sum(d['facturado'] + d['fr'] for d in dados.values())
    rows = [
        {'cells': [loc, str(info['clientes']), f'{fmt_kz(info["facturado"])}',
                   f'{fmt_kz(info["fr"])}', f'{fmt_kz(info["recebido"])}',
                   f'{fmt_kz(info["facturado"] + info["fr"])}']}
        for loc, info in sorted(dados.items(), key=lambda x: x[1]['facturado'] + x[1]['fr'], reverse=True)
    ]

    return {
        'report_name': 'Receita por Localizacao',
        'report_subtitle': 'Facturacao agrupada por localizacao do cliente',
        'summary_cards': [
            {'label': 'Localizacoes', 'value': str(len(dados)), 'color': 'primary'},
            {'label': 'Receita Total', 'value': f'{fmt_kz(total_geral)} Kz', 'color': 'success'},
        ],
        'columns': ['Localizacao', 'Clientes', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
        'rows': rows,
        'filtros': {},
    }


def _dados_receita_despachante(request):
    filtro = _get_user_filter(request)
    clientes = Cliente.objects.filter(**filtro) if filtro else Cliente.objects.all()
    despachantes = Usuario.objects.filter(status='Ativo', papel__in=['Despachante Oficial', 'Administrador'])

    qs_f = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    qs_r = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
    qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')

    facturas_by = {r['cliente__usuario_id']: float(r['total'])
                   for r in qs_f.values('cliente__usuario_id').annotate(total=Sum('valor_total'))
                   if r['cliente__usuario_id'] is not None}
    recibos_by = {r['cliente__usuario_id']: float(r['total'])
                  for r in qs_r.values('cliente__usuario_id').annotate(total=Sum('valor_recebido'))
                  if r['cliente__usuario_id'] is not None}
    fr_by = {r['cliente__usuario_id']: float(r['total'])
             for r in qs_fr.values('cliente__usuario_id').annotate(total=Sum('valor'))
             if r['cliente__usuario_id'] is not None}

    clientes_by_usu = {}
    for c in clientes.filter(usuario_id__isnull=False):
        clientes_by_usu[c.usuario_id] = clientes_by_usu.get(c.usuario_id, 0) + 1

    rows = []
    total_geral = 0
    for d in despachantes:
        uid = d.pk
        if uid not in facturas_by and uid not in fr_by and uid not in recibos_by and uid not in clientes_by_usu:
            continue
        tf = facturas_by.get(uid, 0)
        tr = recibos_by.get(uid, 0)
        tfr = fr_by.get(uid, 0)
        receita = tf + tfr
        total_geral += receita
        rows.append({
            'cells': [d.nome, d.papel, str(clientes_by_usu.get(uid, 0)),
                      f'{fmt_kz(tf)}', f'{fmt_kz(tfr)}', f'{fmt_kz(tr)}', f'{fmt_kz(receita)}'],
            'sort_value': receita,
        })
    rows.sort(key=lambda r: r.get('sort_value', 0), reverse=True)

    return {
        'report_name': 'Receita por Despachante',
        'report_subtitle': 'Facturacao e recebimentos agrupados por despachante',
        'summary_cards': [
            {'label': 'Despachantes', 'value': str(len(rows)), 'color': 'primary'},
            {'label': 'Receita Total', 'value': f'{fmt_kz(total_geral)} Kz', 'color': 'success'},
        ],
        'columns': ['Despachante', 'Perfil', 'Clientes', 'Facturas', 'F-Recibo', 'Recebido', 'Receita Total'],
        'rows': rows,
        'filtros': {},
    }


def _dados_dashboard(request):
    clientes = _get_clientes(request)

    qs_fact = FacturaCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    tot_fact = float(qs_fact.aggregate(t=Sum('valor_total'))['t'] or 0)
    tot_pago = float(qs_fact.aggregate(t=Sum('valor_pago'))['t'] or 0)

    qs_rec = ReciboCliente.objects.filter(cliente__in=clientes).exclude(estado='Cancelado')
    tot_rec = float(qs_rec.aggregate(t=Sum('valor_recebido'))['t'] or 0)

    qs_fr = FacturaRecibo.objects.filter(cliente__in=clientes).exclude(estado='Cancelada')
    tot_fr = float(qs_fr.aggregate(t=Sum('valor'))['t'] or 0)

    tot_recebido = tot_rec + tot_fr
    margem = (tot_recebido / tot_fact * 100) if tot_fact else 0
    a_receber = tot_fact - tot_pago

    total_clientes = clientes.count()
    clientes_divida = clientes.filter(saldo_conta_corrente__lt=0).count()
    pct_inad = (clientes_divida / total_clientes * 100) if total_clientes else 0

    pagas = qs_fact.filter(estado='Paga').count()
    pendentes = qs_fact.filter(estado__in=['Pendente', 'Parcialmente Paga']).count()

    top_totals = (
        FacturaCliente.objects
        .filter(cliente__in=clientes.filter(ativo=True))
        .exclude(estado='Cancelada')
        .values('cliente__nome')
        .annotate(total=Sum('valor_total'))
        .filter(total__gt=0)
        .order_by('-total')[:10]
    )
    rows = [[t['cliente__nome'][:40], fmt_kz(t['total'])] for t in top_totals]

    return {
        'report_name': 'Dashboard Financeiro',
        'report_subtitle': 'Painel executivo com indicadores financeiros',
        'summary_cards': [
            {'label': 'Total Facturado', 'value': f'{fmt_kz(tot_fact)} Kz', 'color': 'primary'},
            {'label': 'Total Recebido', 'value': f'{fmt_kz(tot_recebido)} Kz', 'color': 'success'},
            {'label': 'A Receber', 'value': f'{fmt_kz(a_receber)} Kz', 'color': 'warning'},
            {'label': 'Margem Recebimento', 'value': f'{margem:.1f}%', 'color': 'info'},
            {'label': 'Facturas Pagas', 'value': str(pagas), 'color': 'success'},
            {'label': 'Facturas Pendentes', 'value': str(pendentes), 'color': 'warning'},
            {'label': 'Taxa Inadimplencia', 'value': f'{pct_inad:.1f}%', 'color': 'danger'},
            {'label': 'Total Clientes', 'value': str(total_clientes), 'color': 'primary'},
        ],
        'columns': ['Cliente', 'Facturacao Total'],
        'rows': rows,
        'extra_tables': [],
        'filtros': {},
    }


# ── Mapa de relatorios ──────────────────────────────────────────────────────

_RELATORIOS_MAP = {
    'dashboard': _dados_dashboard,
    'facturacao': _dados_facturacao,
    'recibos': _dados_recibos,
    'requisicao-fundos': _dados_requisicoes_fundos,
    'notas-credito': _dados_notas_credito,
    'notas-debito': _dados_notas_debito,
    'contas-receber': _dados_contas_receber,
    'clientes-devedores': _dados_clientes_devedores,
    'fluxo-caixa': _dados_fluxo_caixa,
    'demonstrativo-receitas': _dados_demonstrativo_receitas,
    'balancete': _dados_balancete,
    'indicadores-cobranca': _dados_indicadores_cobranca,
    'receita-cliente': _dados_receita_cliente,
    'receita-localizacao': _dados_receita_localizacao,
    'receita-despachante': _dados_receita_despachante,
}


# ── View principal de PDF ───────────────────────────────────────────────────

@requer_sessao_ativa
def relatorio_pdf(request, tipo):
    """Gera PDF profissional para o relatorio especificado."""
    dados_fn = _RELATORIOS_MAP.get(tipo)
    if not dados_fn:
        return HttpResponse('Tipo de relatorio invalido', status=404)

    if not _user_tem_acesso_total(request):
        from users.permissoes import usuario_tem_permissao
        if not usuario_tem_permissao(request, 'ver_relatorios_operacionais'):
            papel = request.session.get('usuario', {}).get('papel', '')
            if papel not in ('Administrador', 'Despachante Oficial'):
                return HttpResponse('Sem permissão para aceder a relatórios.', status=403)

    try:
        dados = dados_fn(request)
        banca = _get_banca(request)

        pdf_bytes = gerar_pdf_relatorio(
            report_name=dados['report_name'],
            report_subtitle=dados['report_subtitle'],
            columns=dados.get('columns', []),
            rows=dados.get('rows', []),
            summary_cards=dados.get('summary_cards'),
            extra_tables=dados.get('extra_tables'),
            filtros=dados.get('filtros'),
            banca=banca,
            request=request,
            landscape_mode=True,
        )

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"Relatorio_{tipo}_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        logger.error('Erro ao gerar PDF do relatorio %s: %s', tipo, str(e), exc_info=True)
        return HttpResponse(f'Erro ao gerar PDF: {str(e)}', status=500)
