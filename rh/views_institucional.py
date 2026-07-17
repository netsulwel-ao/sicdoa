"""
Views do RH Institucional — replicam a mesma lógica do RH dos Despachantes
mas para os colaboradores institucionais (equipa da instituição).
Acesso: Administrador ou utilizadores com permissões RH Institucionais.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator
from django.contrib import messages
from django.core.exceptions import ValidationError
from decimal import Decimal

from utils.format_kz import fmt_kz
from utils.email_utils import gerar_senha_aleatoria, enviar_senha_colaborador
from utils.email_utils import enviar_resultado_candidatura, enviar_convocatoria_entrevista
from utils.validators import email_ja_existe
from .tax_utils import _dec, _hash_password, _calcular_irt, MESES
from .acesso import obter_acesso_inst, obter_acesso_inst_modulo
from users.models import (
    ColaboradorInstitucional, PresencaInstitucional, FeriasInstitucional,
    CicloAvaliacaoInstitucional, AvaliacaoInstitucional,
    ProcessamentoSalarialInstitucional, ReciboSalarialInstitucional,
    SubsidioInstitucional, SubsidioReciboInstitucional,
    VagaInstitucional, CandidaturaInstitucional, EntrevistaInstitucional,
    PlanoIntegracaoInstitucional, TarefaIntegracaoInstitucional,
    MetricaAvaliacaoInstitucional, NotaMetricaInstitucional,
)

# MESES imported from tax_utils


# ─── Helpers ─────────────────────────────────────────────────────────────

def _requer_inst(fn):
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        if not obter_acesso_inst(request):
            messages.error(request, 'Acesso restrito ao RH Institucional.')
            return redirect('dashboard')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _requer_inst_modulo(*modulos):
    def decorator(fn):
        def wrapper(request, *args, **kwargs):
            if not request.session.get('usuario_id'):
                return redirect('login')
            acesso = False
            for m in modulos:
                if obter_acesso_inst_modulo(request, m):
                    acesso = True
                    break
            if not acesso:
                messages.error(request, 'Não tem permissão para aceder a esta página.')
                return redirect('rh_inst_dashboard')
            return fn(request, *args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


def _ctx_inst(request, sub='', extra=None):
    u = request.session['usuario']
    from users.permissoes import get_usuario_permissoes
    user_permissoes = get_usuario_permissoes(request)
    ctx = {
        'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
        'active_menu': 'RH_INST', 'active_sub': sub,
        'user_permissoes': user_permissoes,
    }
    if extra:
        ctx.update(extra)
    return ctx


# _dec, _calcular_irt, _hash_password imported from tax_utils


def marcar_ferias_no_registo_inst(pedido):
    from datetime import timedelta
    data = pedido.data_inicio
    while data <= pedido.data_fim:
        if data.weekday() < 5:
            PresencaInstitucional.objects.update_or_create(
                colaborador=pedido.colaborador, data=data,
                defaults={
                    'tipo': 'Ferias', 'estado': 'Aprovado',
                    'hora_entrada': None, 'hora_saida': None,
                    'horas_extras': 0, 'justificacao': '',
                },
            )
        data += timedelta(days=1)


def _gerar_pdf_processamento_inst(processamento, request):
    """Gera PDF do processamento salarial institucional no layout profissional (padrao Requisicao de Fundos).
    Retorna um BytesIO com o PDF gerado em memoria."""
    import logging as _log
    _logger = _log.getLogger(__name__)
    import io
    import qrcode as _qr
    from datetime import datetime
    from decimal import Decimal
    from django.utils import timezone as _tz
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.flowables import HRFlowable
    try:
        from reportlab.platypus import Image as RLImage
    except ImportError:
        RLImage = None
    from users.models import Usuario

    try:
        recibos = processamento.recibos.select_related('colaborador').prefetch_related(
            'subsidios_vinculados__subsidio'
        ).all()
        estado_display = processamento.get_estado_display()

        PAGE_W, PAGE_H = A4
        MARGIN = 0.7 * cm
        W = PAGE_W - 2 * MARGIN

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=0.5 * cm, bottomMargin=1.0 * cm,
            title=f"Processamento Salarial Institucional {processamento.mes:02d}/{processamento.ano}",
        )

        COR_PRIMARIO = colors.HexColor('#0f172a')
        COR_SECUNDARIO = colors.white
        COR_CINZA = colors.HexColor('#64748b')
        COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
        COR_BORDA = colors.HexColor('#cbd5e1')
        COR_BRANCO = colors.white
        COR_HEADER = colors.white
        COR_VERDE = colors.HexColor('#059669')
        COR_VERMELHO = colors.HexColor('#dc2626')

        def st(name, **kw):
            defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRIMARIO, leading=11)
            defaults.update(kw)
            return ParagraphStyle(name, **defaults)

        def _safe(text):
            if not text:
                return ''
            from django.utils.html import escape as _esc
            return _esc(str(text))

        # Dados do utilizador da sessao (administrador da instituicao)
        usuario = request.session.get('usuario', {})
        nome_txt = _safe(usuario.get('nome', 'ADMINISTRACAO INSTITUCIONAL'))
        nif_txt = usuario.get('nif', 'N/D') or 'N/D'
        telefone = usuario.get('telefone', '—') or '—'
        email_b = usuario.get('email', '—') or '—'
        responsavel_nome = nome_txt.upper()
        responsavel_nif = nif_txt
        responsavel_cedula = '—'
        responsavel_telefone = telefone
        responsavel_email = email_b

        agora = datetime.now()

        # Totais
        total_bruto = Decimal('0')
        total_subsidios = Decimal('0')
        total_faltas = Decimal('0')
        total_irt = Decimal('0')
        total_inss = Decimal('0')
        total_liquido = Decimal('0')
        for recibo in recibos:
            total_bruto += recibo.bruto
            total_faltas += recibo.outros_descontos
            total_irt += recibo.irt
            total_inss += recibo.inss_trabalhador
            total_liquido += recibo.liquido
            for vinculo in recibo.subsidios_vinculados.all():
                total_subsidios += vinculo.valor

        story = []

        # LOGO (esquerda) + QR CODE (direita)
        from .models import BancaCentral
        _bc = BancaCentral.get_instance()
        col_logo = Paragraph('', st('empty', fontSize=1))
        if _bc and _bc.logo and RLImage:
            try:
                col_logo = RLImage(_bc.logo.path, width=2.4 * cm, height=1.7 * cm)
            except Exception:
                col_logo = Paragraph('', st('empty', fontSize=1))

        qr_data = (
            f"=== PROCESSAMENTO SALARIAL INSTITUCIONAL ===\n"
            f"Periodo: {processamento.mes:02d}/{processamento.ano}\n"
            f"Estado: {estado_display}\n"
            f"Nr Colaboradores: {len(recibos)}\n"
            f"\n--- TOTAIS ---\n"
            f"Total Bruto: {fmt_kz(total_bruto)} KZ\n"
            f"Total Subsidios: {fmt_kz(total_subsidios)} KZ\n"
            f"Total Descontos: {fmt_kz(total_irt + total_inss + total_faltas)} KZ\n"
            f"Total Liquido: {fmt_kz(total_liquido)} KZ\n"
            f"\n--- RESPONSAVEL ---\n"
            f"Nome: {responsavel_nome}\n"
            f"NIF: {responsavel_nif}\n"
        )
        _qr_buf = io.BytesIO()
        _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
        _qr_obj.add_data(qr_data)
        _qr_obj.make(fit=True)
        _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
        _qr_buf.seek(0)
        qr_flowable = RLImage(_qr_buf, width=1.9 * cm, height=1.9 * cm) if RLImage else Paragraph('', st('empty', fontSize=1))

        top_line = Table([[col_logo, qr_flowable]], colWidths=[W - 1.9 * cm, 1.9 * cm])
        top_line.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(top_line)
        story.append(Spacer(1, 0.15 * cm))

        # BLOCO EMPRESA (esquerda) + INFO DOCUMENTO (direita)
        empresa_info = (
            f'<font size="9"><b>{nome_txt}</b></font><br/>'
            f'<font size="7.5" color="#334155">Tel: {telefone}</font><br/>'
            f'<font size="7.5" color="#334155">Email: {email_b}</font><br/>'
            f'<font size="7.5" color="#334155">NIF: {nif_txt}</font>'
        )
        doc_info = (
            f'<font size="7.5">Processamento Salarial Institucional</font><br/>'
            f'<font size="9"><b>{processamento.mes:02d}/{processamento.ano}</b></font><br/>'
            f'<font size="7.5" color="#334155">Estado: {estado_display}</font><br/>'
            f'<font size="7.5" color="#334155">Nr Colaboradores: {len(recibos)}</font>'
        )
        header_body = Table([[
            Paragraph(empresa_info, st('empresa_info', fontSize=7.5, leading=10)),
            Paragraph(doc_info, st('doc_info', fontSize=7.5, leading=10, alignment=TA_RIGHT)),
        ]], colWidths=[W * 0.55, W * 0.45])
        header_body.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_body)
        story.append(Spacer(1, 0.35 * cm))

        # TITULO DO DOCUMENTO
        story.append(Paragraph('<font size="7.5">Original</font>', st('original', fontSize=7.5)))
        story.append(Paragraph(
            f'<font size="12"><b>Processamento Salarial Institucional ({processamento.mes:02d}/{processamento.ano})</b></font>',
            st('titulo', fontSize=12)
        ))
        story.append(Spacer(1, 0.2 * cm))

        # DADOS DO DOCUMENTO (linha)
        from .tax_utils import MESES as _MESES
        mes_nome = _MESES[processamento.mes - 1] if 1 <= processamento.mes <= 12 else str(processamento.mes)
        dados_doc_header = [
            Paragraph('<b>Periodo</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Data Processamento</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Data Pagamento</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Nr Colaboradores</b>', st('ddh', fontSize=7.5)),
            Paragraph('<b>Estado</b>', st('ddh', fontSize=7.5)),
        ]
        dados_doc_valores = [
            Paragraph(f'{mes_nome} {processamento.ano}', st('ddv', fontSize=7.5)),
            Paragraph(_tz.now().strftime('%d/%m/%Y'), st('ddv', fontSize=7.5)),
            Paragraph(_tz.now().strftime('%d/%m/%Y'), st('ddv', fontSize=7.5)),
            Paragraph(str(len(recibos)), st('ddv', fontSize=7.5)),
            Paragraph(estado_display, st('ddv', fontSize=7.5)),
        ]
        t_dados_doc = Table([dados_doc_header, dados_doc_valores], colWidths=[W / 5] * 5)
        t_dados_doc.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_dados_doc)
        story.append(Paragraph(
            f'<font size="7" color="#64748b">Observacoes: Comprovante de pagamento referente ao periodo {processamento.mes:02d}/{processamento.ano}</font>',
            st('obs', fontSize=7)
        ))
        story.append(Spacer(1, 0.3 * cm))

        # TABELA DE ITENS
        itens_header = [
            Paragraph('<b>Colaborador</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO)),
            Paragraph('<b>Salario Base</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>Subsidios</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>Bruto</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>Faltas</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>IRT</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>INSS 3%</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
            Paragraph('<b>Liquido</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
        ]
        itens_rows = [itens_header]

        for recibo in recibos:
            total_sub = Decimal('0')
            for vinculo in recibo.subsidios_vinculados.all():
                total_sub += vinculo.valor
            itens_rows.append([
                Paragraph(_safe(recibo.colaborador.nome[:35]), st('ic', fontSize=7)),
                Paragraph(fmt_kz(recibo.salario_base), st('ic', fontSize=7, alignment=TA_RIGHT)),
                Paragraph(fmt_kz(total_sub), st('ic', fontSize=7, alignment=TA_RIGHT)),
                Paragraph(fmt_kz(recibo.bruto), st('ic', fontSize=7, alignment=TA_RIGHT)),
                Paragraph(fmt_kz(recibo.outros_descontos), st('ic', fontSize=7, alignment=TA_RIGHT, textColor=COR_VERMELHO if recibo.outros_descontos else COR_PRIMARIO)),
                Paragraph(fmt_kz(recibo.irt), st('ic', fontSize=7, alignment=TA_RIGHT)),
                Paragraph(fmt_kz(recibo.inss_trabalhador), st('ic', fontSize=7, alignment=TA_RIGHT)),
                Paragraph(fmt_kz(recibo.liquido), st('ic', fontSize=7, alignment=TA_RIGHT, textColor=COR_VERDE)),
            ])

        t_itens = Table(itens_rows, colWidths=[W*0.22, W*0.11, W*0.11, W*0.11, W*0.11, W*0.11, W*0.11, W*0.12])
        t_itens.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR_BRANCO, COR_CINZA_CLARO]),
        ]))
        story.append(t_itens)
        story.append(Spacer(1, 0.2 * cm))

        # TOTAIS + SUMARIO
        from financeiro.views import valor_por_extenso as _valor_ext

        totais_rows = [
            [Paragraph('<b>Totais</b>', st('toh', fontSize=7, textColor=COR_PRIMARIO)),
             Paragraph('<b>Valor</b>', st('toh', fontSize=7, textColor=COR_PRIMARIO, alignment=TA_RIGHT))],
            [Paragraph('Total Bruto', st('toc', fontSize=7)),
             Paragraph(f'{fmt_kz(total_bruto)} KZ', st('toc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('Total Subsidios', st('toc', fontSize=7)),
             Paragraph(f'{fmt_kz(total_subsidios)} KZ', st('toc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('Total Faltas/Descontos', st('toc', fontSize=7)),
             Paragraph(f'{fmt_kz(total_faltas)} KZ', st('toc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('Total IRT', st('toc', fontSize=7)),
             Paragraph(f'{fmt_kz(total_irt)} KZ', st('toc', fontSize=7, alignment=TA_RIGHT))],
            [Paragraph('Total INSS (3%)', st('toc', fontSize=7)),
             Paragraph(f'{fmt_kz(total_inss)} KZ', st('toc', fontSize=7, alignment=TA_RIGHT))],
        ]
        t_totais = Table(totais_rows, colWidths=[W * 0.55 * 0.55, W * 0.55 * 0.45])
        t_totais.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 0), (-1, 0), 1.0, COR_CINZA),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, COR_BORDA),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR_BRANCO, COR_CINZA_CLARO]),
        ]))

        ref_texto = (
            f'<font size="7.5"><b>Referencia do Processamento</b></font><br/>'
            f'<font size="7" color="#334155">Periodo: {processamento.mes:02d}/{processamento.ano}</font><br/>'
            f'<font size="7" color="#334155">Nr Colaboradores: {len(recibos)}</font><br/>'
            f'<font size="7" color="#334155">Codigo: PROC-INST-{processamento.pk:04d}</font>'
        )
        bloco_esquerdo = [
            [t_totais],
            [Spacer(1, 0.25 * cm)],
            [Paragraph(ref_texto, st('ref_proc', fontSize=7, leading=10))],
        ]
        t_bloco_esquerdo = Table(bloco_esquerdo, colWidths=[W * 0.55])
        t_bloco_esquerdo.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        sumario_rows = [
            [Paragraph('<b>Sumario</b>', st('sum_h', fontSize=8, fontName='Helvetica-Bold', textColor=COR_PRIMARIO))],
            [Spacer(1, 0.15 * cm)],
            [Paragraph(f'<font size="7">Total Bruto: <b>{fmt_kz(total_bruto)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">Total Subsidios: <b>{fmt_kz(total_subsidios)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Paragraph(f'<font size="7">Total Descontos: <b>{fmt_kz(total_faltas + total_irt + total_inss)} KZ</b></font>',
                       st('sum_l', fontSize=7, leading=10))],
            [Spacer(1, 0.15 * cm)],
            [Paragraph(f'<font size="10" color="#0f172a"><b>Total Liquido: {fmt_kz(total_liquido)} KZ</b></font>',
                       st('sum_total', fontSize=10, leading=12))],
            [Spacer(1, 0.1 * cm)],
            [Paragraph(f'<font size="6.5" color="#64748b"><i>{_valor_ext(total_liquido)}</i></font>',
                       st('sum_ext', fontSize=6.5, leading=8))],
        ]
        t_sumario = Table(sumario_rows, colWidths=[W * 0.35])
        t_sumario.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), COR_HEADER),
            ('TOPPADDING', (0, 0), (0, 0), 5),
            ('BOTTOMPADDING', (0, 0), (0, 0), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ]))
        bloco_direito = t_sumario

        t_resumo = Table([[t_bloco_esquerdo, '', '', bloco_direito]], colWidths=[W * 0.60, W * 0.02, W * 0.03, W * 0.35])
        t_resumo.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_resumo)
        story.append(Spacer(1, 0.2 * cm))

        # NOTA
        nota_box = Table([[
            Paragraph('<b>Nota</b>', st('nota_h', fontSize=7.5, textColor=COR_PRIMARIO)),
        ]], colWidths=[W])
        nota_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_SECUNDARIO),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, 0), 6),
        ]))
        story.append(nota_box)
        story.append(Paragraph(
            'Os valores referidos neste documento sao os valores liquidos a transferir para as contas dos colaboradores.',
            st('nota_txt', fontSize=7, textColor=COR_CINZA)
        ))
        story.append(Spacer(1, 0.15 * cm))

        # RESPONSAVEL
        story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
        story.append(Spacer(1, 0.15 * cm))
        desp_box = Table([[
            Paragraph('<b>Responsavel</b>', st('desp_h', fontSize=7.5, textColor=COR_PRIMARIO)),
        ]], colWidths=[W])
        desp_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, 0), 6),
        ]))
        story.append(desp_box)
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph(
            f'{responsavel_nome} &nbsp;|&nbsp; NIF: {responsavel_nif}',
            st('desp_l1', fontSize=7.5, textColor=COR_PRIMARIO)
        ))
        story.append(Paragraph(
            f'Tel: {responsavel_telefone} &nbsp;|&nbsp; Email: {responsavel_email}',
            st('desp_l2', fontSize=7, textColor=COR_CINZA)
        ))
        story.append(Spacer(1, 0.15 * cm))

        # ASSINATURA
        story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
        story.append(Spacer(1, 0.1 * cm))
        _assinatura_img = Paragraph('', st('ass_img', fontSize=1))
        if _bc and _bc.assinatura and RLImage:
            try:
                _assinatura_img = RLImage(_bc.assinatura.path, width=4 * cm, height=1.5 * cm)
            except Exception:
                _assinatura_img = Paragraph('', st('ass_img', fontSize=1))
        ass_data = [
            [Paragraph('<b>Assinatura:</b>', st('ass_lab', fontSize=8)),
             Paragraph('', st('ass_spc', fontSize=8))],
            [_assinatura_img, Spacer(1, 0.2 * cm)],
            [HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA),
             HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA)],
            [Paragraph('<font size="7.5"><b>Data:</b> _____/_____/______</font>', st('ass_data', fontSize=7.5)),
             Paragraph(f'<font size="7.5"><b>{nome_txt}</b></font>', st('ass_cli', fontSize=7.5, alignment=TA_CENTER))],
        ]
        assinatura = Table(ass_data, colWidths=[W / 2, W / 2])
        assinatura.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(assinatura)
        story.append(Spacer(1, 0.15 * cm))

        # RODAPE: HASH
        story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor('#e2e2e2')))
        story.append(Spacer(1, 0.1 * cm))
        from financeiro.pdf_utils import _hash_documento
        dados_hash = {
            'tipo': 'Processamento Salarial Institucional',
            'periodo': f'{processamento.mes:02d}/{processamento.ano}',
            'total_liquido': str(total_liquido),
            'pk': processamento.pk,
        }
        hsh = _hash_documento(dados_hash)[:16]
        story.append(Paragraph(
            f'<font size="6" color="#94a3b8"><b>{nome_txt} - {hsh}</b> &nbsp;|&nbsp; '
            f'Processado por programa valido n35/AGT/2019<br/>'
            f'Pag. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>',
            st('footer', fontSize=6)
        ))

        doc.build(story)
        buffer.seek(0)

        processamento.pdf_gerado = True
        processamento.save(update_fields=['pdf_gerado'])

        return buffer
    except Exception:
        _logger.exception("Erro ao gerar PDF institucional do processamento %s", processamento.pk)


# ══════════════════════════════════════════════════════════════════════════
# DASHBOARD INSTITUCIONAL
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
def inst_dashboard_view(request):
    hoje = timezone.now().date()
    stats = {
        'total_colaboradores': ColaboradorInstitucional.objects.count(),
        'colaboradores_activos': ColaboradorInstitucional.objects.filter(estado='Ativo').count(),
        'presencas_hoje': PresencaInstitucional.objects.filter(data=hoje).count(),
        'presencas_pendentes': PresencaInstitucional.objects.filter(estado='Pendente').count(),
        'ferias_pendentes': FeriasInstitucional.objects.filter(estado='Pendente').count(),
        'vagas_abertas': VagaInstitucional.objects.filter(estado='Aberta').count(),
        'candidaturas_recentes': CandidaturaInstitucional.objects.filter(criado_em__date=hoje).count(),
        'ultimo_processamento': ProcessamentoSalarialInstitucional.objects.order_by('-ano', '-mes').first(),
        'ciclos_activos': CicloAvaliacaoInstitucional.objects.filter(estado__in=['Aberto', 'Em Curso']).count(),
        'colaboradores_recentes': ColaboradorInstitucional.objects.order_by('-criado_em')[:5],
    }
    return render(request, 'rh/institucional/dashboard.html',
                  _ctx_inst(request, 'dashboard_inst', {'stats': stats}))


# ══════════════════════════════════════════════════════════════════════════
# SUBSÍDIOS
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidios_view(request):
    subsidios = SubsidioInstitucional.objects.all().order_by('codigo')
    paginator = Paginator(subsidios, 8)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'rh/institucional/subsidios_lista.html',
                  _ctx_inst(request, 'subsidios_inst', {
                      'subsidios': page, 'page_obj': page,
                  }))


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_novo_view(request):
    def _render(extra=None):
        return render(request, 'rh/institucional/subsidio_form.html',
                      _ctx_inst(request, 'subsidios_inst', {
                          'subsidio': None, 'form': {},
                          'tipos_calculo': SubsidioInstitucional.TIPOS_CALCULO,
                          'colaboradores': ColaboradorInstitucional.objects.filter(estado='Ativo').order_by('nome'),
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': _dec(request.POST.get('percentual')) if request.POST.get('percentual') else None,
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador.'})
        if dados['obrigatorio']:
            dados['apenas_especificos'] = False
        if SubsidioInstitucional.objects.filter(codigo=dados['codigo']).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        subsidio = SubsidioInstitucional.objects.create(**dados)
        if dados['apenas_especificos']:
            ids = request.POST.getlist('colaboradores_ids')
            subsidio.colaboradores_especificos.set(
                ColaboradorInstitucional.objects.filter(pk__in=ids)
            )
        return redirect('rh_inst_subsidios')

    return _render()


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_editar_view(request, pk):
    subsidio = get_object_or_404(SubsidioInstitucional, pk=pk)

    def _render(extra=None):
        form_data = {
            'nome': subsidio.nome, 'codigo': subsidio.codigo,
            'tipo_calculo': subsidio.tipo_calculo,
            'valor_padrao': subsidio.valor_padrao, 'percentual': subsidio.percentual,
            'ativo': subsidio.ativo, 'obrigatorio': subsidio.obrigatorio,
            'apenas_especificos': subsidio.apenas_especificos,
            'descricao': subsidio.descricao,
        }
        return render(request, 'rh/institucional/subsidio_form.html',
                      _ctx_inst(request, 'subsidios_inst', {
                          'subsidio': subsidio, 'form': form_data,
                          'tipos_calculo': SubsidioInstitucional.TIPOS_CALCULO,
                          'colaboradores': ColaboradorInstitucional.objects.filter(estado='Ativo').order_by('nome'),
                          'colaboradores_selecionados': list(subsidio.colaboradores_especificos.values_list('pk', flat=True)),
                          **(extra or {}),
                      }))

    if request.method == 'POST':
        apenas_especificos = request.POST.get('apenas_especificos') == 'on'
        dados = {
            'nome': request.POST.get('nome', '').strip(),
            'codigo': request.POST.get('codigo', '').strip().upper(),
            'tipo_calculo': request.POST.get('tipo_calculo', 'FIXO'),
            'valor_padrao': _dec(request.POST.get('valor_padrao', '0')),
            'percentual': _dec(request.POST.get('percentual')) if request.POST.get('percentual') else None,
            'ativo': request.POST.get('ativo') == 'on',
            'obrigatorio': request.POST.get('obrigatorio') == 'on',
            'apenas_especificos': apenas_especificos,
            'descricao': request.POST.get('descricao', '').strip(),
        }
        if not dados['nome']:
            return _render({'erro': 'Nome do subsídio é obrigatório.'})
        if not dados['codigo']:
            return _render({'erro': 'Código do subsídio é obrigatório.'})
        if dados['tipo_calculo'] == 'PERCENTUAL' and not dados['percentual']:
            return _render({'erro': 'Percentual é obrigatório para tipo Percentual.'})
        if apenas_especificos and not request.POST.getlist('colaboradores_ids'):
            return _render({'erro': 'Selecione pelo menos um colaborador.'})
        if dados['obrigatorio']:
            dados['apenas_especificos'] = False
        if SubsidioInstitucional.objects.filter(codigo=dados['codigo']).exclude(pk=pk).exists():
            return _render({'erro': 'Já existe um subsídio com este código.'})

        for campo, valor in dados.items():
            setattr(subsidio, campo, valor)
        subsidio.save()
        if subsidio.apenas_especificos:
            ids = request.POST.getlist('colaboradores_ids')
            subsidio.colaboradores_especificos.set(ColaboradorInstitucional.objects.filter(pk__in=ids))
        else:
            subsidio.colaboradores_especificos.clear()
        return redirect('rh_inst_subsidios')

    return _render()


@_requer_inst
@_requer_inst_modulo('subsidios')
def inst_subsidio_apagar_view(request, pk):
    subsidio = get_object_or_404(SubsidioInstitucional, pk=pk)
    if request.method == 'POST':
        if subsidio.subsidioreciboinstitucional_set.exists():
            return render(request, 'rh/institucional/subsidio_erro.html',
                          _ctx_inst(request, 'subsidios_inst', {
                              'subsidio': subsidio,
                              'erro': 'Subsídio está vinculado a recibos salariais e não pode ser removido.',
                          }))
        subsidio.delete()
        messages.success(request, f'Subsídio "{subsidio.nome}" removido.')
        return redirect('rh_inst_subsidios')
    return render(request, 'rh/institucional/subsidio_apagar.html',
                  _ctx_inst(request, 'subsidios_inst', {'subsidio': subsidio}))


# ══════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO SALARIAL
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salarios_view(request):
    processamentos = ProcessamentoSalarialInstitucional.objects.annotate(
        total_recibos=Count('recibos'),
    ).prefetch_related('recibos').order_by('-ano', '-mes')

    paginator = Paginator(processamentos, 8)
    pagina = paginator.get_page(request.GET.get('pagina', 1))

    return render(request, 'rh/institucional/salarios_lista.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'processamentos': pagina, 'page_obj': pagina,
                      'total': processamentos.count(),
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_novo_view(request):
    if request.method == 'POST':
        mes = int(request.POST.get('mes') or 1)
        ano = int(request.POST.get('ano') or timezone.now().year)
        proc, criado = ProcessamentoSalarialInstitucional.objects.get_or_create(
            mes=mes, ano=ano, defaults={'estado': 'Rascunho'}
        )
        if not criado:
            return redirect('rh_inst_salario_detalhe', pk=proc.pk)

        subsidios_inst = list(SubsidioInstitucional.objects.filter(ativo=True))
        subsidio_colab_ids = {}
        for s in subsidios_inst:
            if s.apenas_especificos:
                subsidio_colab_ids[s.pk] = set(s.colaboradores_especificos.values_list('id', flat=True))

        colaboradores_ids = request.POST.getlist('colaboradores')
        colaboradores_qs = ColaboradorInstitucional.objects.filter(estado='Ativo')
        if colaboradores_ids:
            colaboradores_qs = colaboradores_qs.filter(pk__in=colaboradores_ids)
        for col in colaboradores_qs:
            salario = col.salario_base or Decimal('0')
            faltas = PresencaInstitucional.objects.filter(
                colaborador=col, data__month=mes, data__year=ano,
                tipo__in=['Falta', 'Falta_Justificada'], estado='Aprovado',
            ).count()
            dias_uteis = Decimal('22')
            desconto_faltas = (salario / dias_uteis * faltas).quantize(Decimal('0.01')) if faltas > 0 else Decimal('0')
            salario_apos_faltas = max(salario - desconto_faltas, Decimal('0'))
            irt = _calcular_irt(salario_apos_faltas)
            inss_trab = (salario_apos_faltas * Decimal('0.03')).quantize(Decimal('0.01'))
            inss_ent = (salario_apos_faltas * Decimal('0.08')).quantize(Decimal('0.01'))

            subsidios_aplicaveis = []
            for subsidio in subsidios_inst:
                if subsidio.apenas_especificos:
                    if col.id in subsidio_colab_ids.get(subsidio.pk, set()):
                        subsidios_aplicaveis.append(subsidio)
                else:
                    subsidios_aplicaveis.append(subsidio)

            total_subsidios = Decimal('0')
            for subsidio in subsidios_aplicaveis:
                if subsidio.tipo_calculo == 'PERCENTUAL':
                    if subsidio.percentual and salario:
                        total_subsidios += (salario * subsidio.percentual) / 100
                    else:
                        total_subsidios += subsidio.valor_padrao
                elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                    total_subsidios += subsidio.valor_padrao * 22
                elif subsidio.tipo_calculo == 'DEPENDENTES':
                    total_subsidios += subsidio.valor_padrao * 1
                else:
                    total_subsidios += subsidio.valor_padrao

            recibo, recibo_criado = ReciboSalarialInstitucional.objects.get_or_create(
                processamento=proc, colaborador=col,
                defaults={
                    'salario_base': salario,
                    'subsidio_alimentacao': Decimal('0'),
                    'subsidio_transporte': Decimal('0'),
                    'outros_subsidios': total_subsidios,
                    'outros_descontos': desconto_faltas,
                    'irt': irt,
                    'inss_trabalhador': inss_trab,
                    'inss_entidade': inss_ent,
                }
            )

            if recibo_criado:
                for subsidio in subsidios_aplicaveis:
                    if subsidio.tipo_calculo == 'PERCENTUAL':
                        v = (salario * subsidio.percentual) / 100 if subsidio.percentual and salario else subsidio.valor_padrao
                    elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                        v = subsidio.valor_padrao * 22
                    elif subsidio.tipo_calculo == 'DEPENDENTES':
                        v = subsidio.valor_padrao * 1
                    else:
                        v = subsidio.valor_padrao
                    SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=recibo, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )

        if proc.total_liquido == 0:
            proc.delete()
            hoje = timezone.now().date()
            cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
            anos = list(range(2023, hoje.year + 2))
            return render(request, 'rh/institucional/salario_novo.html',
                          _ctx_inst(request, 'salarios_inst', {
                              'colaboradores': cols, 'meses': list(enumerate(MESES, 1)),
                              'anos': anos, 'ano_atual': hoje.year,
                              'erro': 'Total líquido é 0,00 KZ. Verifique salários base e subsídios.',
                          }))
        return redirect('rh_inst_salario_detalhe', pk=proc.pk)

    hoje = timezone.now().date()
    cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
    anos = list(range(2023, hoje.year + 2))
    return render(request, 'rh/institucional/salario_novo.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'colaboradores': cols, 'meses': list(enumerate(MESES, 1)),
                      'anos': anos, 'ano_atual': hoje.year,
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_detalhe_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    if request.method == 'POST':
        if proc.estado == 'Pago':
            messages.error(request, 'Processamento Pago não pode ser alterado.')
            return redirect('rh_inst_salario_detalhe', pk=proc.pk)

        action = request.POST.get('accao', '')
        if action == 'salvar':
            subsidios_ativos = list(SubsidioInstitucional.objects.filter(ativo=True))
            for r in recibos:
                p = f'rec_{r.pk}_'
                total_subs = Decimal('0')
                subsidios_aplicaveis = []
                for subsidio in subsidios_ativos:
                    if subsidio.apenas_especificos:
                        if subsidio.colaboradores_especificos.filter(id=r.colaborador.id).exists():
                            subsidios_aplicaveis.append(subsidio)
                    else:
                        subsidios_aplicaveis.append(subsidio)

                for subsidio in subsidios_aplicaveis:
                    v = _dec(request.POST.get(f'{p}subsidio_{subsidio.pk}', '0'))

                    vinculo, _ = SubsidioReciboInstitucional.objects.get_or_create(
                        recibo=r, subsidio=subsidio,
                        defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
                    )
                    if not _:
                        vinculo.valor = v
                        vinculo.save()
                    total_subs += v

                SubsidioReciboInstitucional.objects.filter(recibo=r).exclude(
                    subsidio_id__in=[s.pk for s in subsidios_aplicaveis]
                ).delete()
                r.outros_subsidios = total_subs
                r.subsidio_alimentacao = Decimal('0')
                r.subsidio_transporte = Decimal('0')
                faltas_count = int(request.POST.get(f'{p}faltas', '0') or '0')
                r.outros_descontos = (r.salario_base / Decimal('22') * faltas_count).quantize(Decimal('0.01')) if faltas_count > 0 else Decimal('0')
                base_impostos = r.base_calculo_impostos
                r.irt = _calcular_irt(base_impostos)
                r.inss_trabalhador = (base_impostos * Decimal('0.03')).quantize(Decimal('0.01'))
                r.inss_entidade = (base_impostos * Decimal('0.08')).quantize(Decimal('0.01'))
                r.save()
            messages.success(request, 'Alterações guardadas.')

        elif action == 'processar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total líquido é 0,00 KZ. Verifique os dados.')
                return redirect('rh_inst_salario_detalhe', pk=proc.pk)
            proc.estado = 'Processado'
            proc.processado_em = timezone.now()
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} processado.')

        elif action == 'pagar':
            if proc.total_liquido == 0:
                messages.error(request, 'Total liquido e 0,00 KZ.')
                return redirect('rh_inst_salario_detalhe', pk=proc.pk)
            proc.estado = 'Pago'
            proc.save()
            messages.success(request, f'Processamento {proc.mes:02d}/{proc.ano} pago.')

        elif action == 'reabrir':
            if proc.estado == 'Processado':
                proc.estado = 'Rascunho'
                proc.processado_em = None
                proc.save()
                messages.success(request, 'Processamento reaberto.')
            else:
                messages.error(request, 'Apenas processamentos "Processado" podem ser reabertos.')
        return redirect('rh_inst_salario_detalhe', pk=proc.pk)

    subsidios_ativos = SubsidioInstitucional.objects.filter(ativo=True)
    tem_faltantes = False
    for r in recibos:
        for subsidio in subsidios_ativos:
            if not subsidio.obrigatorio:
                continue
            if SubsidioReciboInstitucional.objects.filter(recibo=r, subsidio=subsidio).exists():
                continue
            tem_faltantes = True
            if subsidio.tipo_calculo == 'PERCENTUAL':
                v = (r.salario_base * subsidio.percentual) / 100 if subsidio.percentual and r.salario_base else subsidio.valor_padrao
            elif subsidio.tipo_calculo == 'DIAS_TRABALHO':
                v = subsidio.valor_padrao * 22
            elif subsidio.tipo_calculo == 'DEPENDENTES':
                v = subsidio.valor_padrao * 1
            else:
                v = subsidio.valor_padrao
            SubsidioReciboInstitucional.objects.get_or_create(
                recibo=r, subsidio=subsidio,
                defaults={'valor': v, 'valor_padrao': subsidio.valor_padrao},
            )
    if tem_faltantes:
        recibos = proc.recibos.select_related('colaborador').prefetch_related('subsidios_vinculados__subsidio').all()

    return render(request, 'rh/institucional/salario_detalhe.html',
                  _ctx_inst(request, 'salarios_inst', {
                      'proc': proc, 'recibos': recibos, 'meses': MESES,
                      'subsidios_ativos': subsidios_ativos,
                  }))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_apagar_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado == 'Pago':
        messages.error(request, 'Processamentos Pago são permanentes.')
        return redirect('rh_inst_salarios')
    if request.method == 'POST':
        label = f'{proc.mes:02d}/{proc.ano}'
        proc.delete()
        messages.success(request, f'Processamento {label} apagado.')
        return redirect('rh_inst_salarios')
    return render(request, 'rh/institucional/salario_apagar.html',
                  _ctx_inst(request, 'salarios_inst', {'proc': proc}))


@_requer_inst
@_requer_inst_modulo('salarios')
def inst_salario_download_view(request, pk):
    proc = get_object_or_404(ProcessamentoSalarialInstitucional, pk=pk)
    if proc.estado != 'Pago':
        return render(request, 'rh/institucional/salario_erro_download.html',
                      _ctx_inst(request, 'salarios_inst', {
                          'proc': proc,
                          'erro': 'PDF disponivel apenas para processamentos "Pago".',
                      }))
    try:
        buffer = _gerar_pdf_processamento_inst(proc, request)
        if buffer is None:
            raise RuntimeError("PDF generation returned None")
        response = HttpResponse(buffer.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="comprovante_pagamento_inst_{proc.mes:02d}_{proc.ano}.pdf"'
        return response
    except Exception as e:
        return render(request, 'rh/institucional/salario_erro_download.html',
                      _ctx_inst(request, 'salarios_inst', {
                          'proc': proc, 'erro': f'Erro ao gerar PDF: {str(e)}',
                      }))


# ══════════════════════════════════════════════════════════════════════════
# RECRUTAMENTO
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vagas_view(request):
    estado_filter = request.GET.get('estado', '')
    search_query = request.GET.get('search', '')
    vagas_qs = VagaInstitucional.objects.all()
    if estado_filter:
        vagas_qs = vagas_qs.filter(estado=estado_filter)
    if search_query:
        vagas_qs = vagas_qs.filter(
            Q(titulo__icontains=search_query) | Q(departamento__icontains=search_query)
        )
    vagas = vagas_qs.annotate(num_candidatos=Count('candidaturas')).order_by('-criado_em')
    paginator = Paginator(vagas, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    from django.utils import timezone
    stats = vagas_qs.aggregate(
        total_vagas=Count('id'),
        vagas_abertas=Count('id', filter=Q(estado='Aberta')),
        vagas_em_analise=Count('id', filter=Q(estado='Em Análise')),
        vagas_encerradas=Count('id', filter=Q(estado='Encerrada')),
        total_candidaturas=Count('candidaturas'),
    )
    stats['candidaturas_hoje'] = CandidaturaInstitucional.objects.filter(
        criado_em__date=timezone.now().date()
    ).count()
    from django.conf import settings
    return render(request, 'rh/institucional/recrutamento_vagas.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'vagas': page_obj, 'stats': stats, 'page_obj': page_obj,
                      'estado_filter': estado_filter, 'search_query': search_query,
                      'site_url': settings.SITE_URL.rstrip('/'),
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_nova_view(request):
    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()
        if not titulo:
            return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                          _ctx_inst(request, 'recrutamento_inst', {
                              'vaga': None, 'erro': 'O título é obrigatório.',
                          }))
        try:
            VagaInstitucional.objects.create(
                titulo=titulo,
                departamento=request.POST.get('departamento', '').strip(),
                descricao=request.POST.get('descricao', '').strip(),
                requisitos=request.POST.get('requisitos', '').strip(),
                salario_min=_dec(request.POST.get('salario_min')) or None,
                salario_max=_dec(request.POST.get('salario_max')) or None,
                vagas_numero=int(request.POST.get('vagas_numero') or 1),
                data_encerramento=request.POST.get('data_encerramento') or None,
            )
            return redirect('rh_inst_vagas')
        except ValidationError as e:
            messages.error(request, str(e))
    return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'vaga': None}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_editar_view(request, pk):
    vaga = get_object_or_404(VagaInstitucional, pk=pk)
    if request.method == 'POST':
        try:
            vaga.titulo = request.POST.get('titulo', '').strip()
            vaga.departamento = request.POST.get('departamento', '').strip()
            vaga.descricao = request.POST.get('descricao', '').strip()
            vaga.requisitos = request.POST.get('requisitos', '').strip()
            vaga.salario_min = _dec(request.POST.get('salario_min')) or None
            vaga.salario_max = _dec(request.POST.get('salario_max')) or None
            vaga.vagas_numero = int(request.POST.get('vagas_numero') or 1)
            vaga.estado = request.POST.get('estado', 'Aberta')
            vaga.data_encerramento = request.POST.get('data_encerramento') or None
            vaga.save()
            return redirect('rh_inst_vagas')
        except ValidationError as e:
            messages.error(request, str(e))
    return render(request, 'rh/institucional/recrutamento_vaga_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'vaga': vaga}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_vaga_eliminar_view(request, pk):
    vaga = get_object_or_404(VagaInstitucional, pk=pk)
    if request.method == 'POST':
        vaga.delete()
        messages.success(request, f'Vaga "{vaga.titulo}" eliminada.')
        return redirect('rh_inst_vagas')
    return redirect('rh_inst_vagas')


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidaturas_view(request, vaga_pk):
    vaga = get_object_or_404(VagaInstitucional, pk=vaga_pk)
    candidaturas_qs = vaga.candidaturas.prefetch_related(
        'entrevistas',
        Prefetch('plano_integracao', queryset=PlanoIntegracaoInstitucional.objects.only('id', 'estado'))
    ).order_by('-criado_em')

    MAPA_ETAPA = {
        'Recebida': 'candidaturas', 'Em Análise': 'candidaturas',
        'Entrevista': 'entrevistas', 'Aprovado': 'integracao', 'Rejeitado': 'candidaturas',
    }
    candidaturas = []
    for c in candidaturas_qs:
        c.etapa_key = MAPA_ETAPA.get(c.estado, 'candidaturas')
        candidaturas.append(c)

    paginator = Paginator(candidaturas, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    etapas = [
        ('candidaturas', 'Candidaturas', 'gray', 'inbox'),
        ('entrevistas', 'Entrevistas', 'blue', 'event'),
        ('integracao', 'Integração', 'green', 'person_check'),
    ]
    return render(request, 'rh/institucional/recrutamento_candidaturas.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'vaga': vaga, 'candidaturas': page_obj,
                      'etapas': etapas, 'page_obj': page_obj,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidatura_detalhe_view(request, pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=pk)
    entrevistas = cand.entrevistas.all()
    plano = getattr(cand, 'plano_integracao', None)
    fluxo_etapas = [
        (1, 'Candidatura', ['Recebida', 'Em Análise']),
        (2, 'Entrevista', ['Entrevista']),
        (3, 'Aprovação', ['Aprovado', 'Rejeitado']),
        (4, 'Integração', []),
    ]
    etapa_map = {'Recebida': 1, 'Em Análise': 1, 'Entrevista': 2, 'Aprovado': 3, 'Rejeitado': 3}
    fluxo_atual = etapa_map.get(cand.estado, 1)
    if plano:
        fluxo_atual = 4
    return render(request, 'rh/institucional/recrutamento_candidatura_detalhe.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'cand': cand, 'entrevistas': entrevistas, 'plano': plano,
                      'fluxo_etapas': fluxo_etapas, 'fluxo_etapa_atual': fluxo_atual,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_candidatura_estado_view(request, pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=pk)
    if request.method == 'POST':
        estado_anterior = cand.estado
        cand.estado = request.POST.get('estado', cand.estado)
        cand.notas = request.POST.get('notas', '').strip()
        cand.save()
        if cand.estado in ('Aprovado', 'Rejeitado') and cand.estado != estado_anterior:
            sucesso, msg = enviar_resultado_candidatura(cand)
            if sucesso:
                messages.success(request, f'Email enviado para {cand.email}.')
            else:
                messages.warning(request, f'Estado atualizado, mas falhou envio de email.')
        else:
            messages.success(request, 'Estado atualizado.')
    return redirect('rh_inst_candidaturas', vaga_pk=cand.vaga.pk)


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_entrevista_nova_view(request, candidatura_pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=candidatura_pk)
    if request.method == 'POST':
        EntrevistaInstitucional.objects.create(
            candidatura=cand,
            data_hora=request.POST.get('data_hora'),
            tipo=request.POST.get('tipo', 'Presencial'),
            local_link=request.POST.get('local_link', '').strip(),
            entrevistador=request.POST.get('entrevistador', '').strip(),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        if cand.estado not in ('Aprovado', 'Rejeitado'):
            cand.estado = 'Entrevista'
            cand.save()
        entrevista = cand.entrevistas.order_by('-criado_em').first()
        if entrevista and cand.email:
            sucesso, msg = enviar_convocatoria_entrevista(entrevista)
            if sucesso:
                messages.success(request, f'Convocatória enviada para {cand.email}.')
            else:
                messages.warning(request, 'Entrevista agendada, mas falhou o envio de email.')
        else:
            messages.success(request, 'Entrevista agendada.')
        return redirect('rh_inst_candidatura_detalhe', pk=cand.pk)
    return render(request, 'rh/institucional/recrutamento_entrevista_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {'cand': cand}))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_entrevista_resultado_view(request, pk):
    entrevista = get_object_or_404(EntrevistaInstitucional, pk=pk)
    if request.method == 'POST':
        entrevista.resultado = request.POST.get('resultado', 'Pendente')
        entrevista.nota = request.POST.get('nota') or None
        entrevista.observacoes = request.POST.get('observacoes', '').strip()
        entrevista.save()
        cand = entrevista.candidatura
        if entrevista.resultado == 'Aprovado':
            cand.estado = 'Aprovado'
            cand.save()
        elif entrevista.resultado == 'Reprovado':
            cand.estado = 'Rejeitado'
            cand.save()
        return redirect('rh_inst_candidatura_detalhe', pk=cand.pk)
    return redirect('rh_inst_candidatura_detalhe', pk=entrevista.candidatura.pk)


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_integracao_nova_view(request, candidatura_pk):
    cand = get_object_or_404(CandidaturaInstitucional, pk=candidatura_pk, estado='Aprovado')
    if hasattr(cand, 'plano_integracao'):
        return redirect('rh_inst_integracao_detalhe', pk=cand.plano_integracao.pk)

    if request.method == 'POST':
        plano = PlanoIntegracaoInstitucional.objects.create(
            candidatura=cand,
            data_inicio=request.POST.get('data_inicio'),
            data_fim_prevista=request.POST.get('data_fim_prevista') or None,
            responsavel=request.POST.get('responsavel', '').strip(),
            notas=request.POST.get('notas', '').strip(),
        )

        if request.POST.get('criar_colaborador') == '1':
            email_col = cand.email.strip() if cand.email else ''
            if email_col and email_ja_existe(email_col):
                messages.error(request, f'O email {email_col} já está registado.')
                return redirect('rh_inst_integracao_detalhe', pk=plano.pk)
            senha_gerada = None
            senha_hash = None
            if email_col:
                senha_gerada = gerar_senha_aleatoria()
                senha_hash = _hash_password(senha_gerada)
            col = ColaboradorInstitucional.objects.create(
                nome=cand.nome,
                email=email_col,
                telefone=cand.telefone,
                area_actuacao=request.POST.get('area_actuacao', 'Outro'),
                data_admissao=request.POST.get('data_inicio'),
                salario_base=_dec(request.POST.get('salario_base')) or None,
                estado='Ativo',
            )
            plano.colaborador = col
            plano.save()

            if email_col and senha_gerada:
                ok, msg = enviar_senha_colaborador(col, senha_gerada)
                if ok:
                    messages.success(request, f'Colaborador criado. Credenciais enviadas para {email_col}.')
                else:
                    messages.warning(request, f'Colaborador criado, mas falhou envio: {msg}')

        tarefas_padrao = [
            'Apresentação à equipa e instalações',
            'Entrega de equipamentos e acessos',
            'Formação inicial sobre processos internos',
            'Revisão de políticas e regulamentos',
            'Acompanhamento pelo responsável durante o período de integração',
        ]
        for t in tarefas_padrao:
            TarefaIntegracaoInstitucional.objects.create(
                plano=plano, titulo=t, prazo=request.POST.get('data_fim_prevista') or None,
            )
        return redirect('rh_inst_integracao_detalhe', pk=plano.pk)

    cargo_sugerido = cand.vaga.titulo
    departamento_sugerido = cand.vaga.departamento or ''
    responsavel_nome = request.session.get('usuario', {}).get('nome', '')
    return render(request, 'rh/institucional/recrutamento_integracao_form.html',
                  _ctx_inst(request, 'recrutamento_inst', {
                      'cand': cand,
                      'cargo_sugerido': cargo_sugerido,
                      'departamento_sugerido': departamento_sugerido,
                      'responsavel_nome': responsavel_nome,
                  }))


@_requer_inst
@_requer_inst_modulo('recrutamento')
def inst_integracao_detalhe_view(request, pk):
    plano = get_object_or_404(PlanoIntegracaoInstitucional, pk=pk)
    tarefas = plano.tarefas.all()
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'tarefa_toggle':
            tarefa = get_object_or_404(TarefaIntegracaoInstitucional, pk=request.POST.get('tarefa_pk'), plano=plano)
            tarefa.concluida = not tarefa.concluida
            tarefa.save()
        elif action == 'tarefa_nova':
            titulo = request.POST.get('titulo', '').strip()
            if titulo:
                TarefaIntegracaoInstitucional.objects.create(
                    plano=plano, titulo=titulo,
                    responsavel=request.POST.get('responsavel', '').strip(),
                    prazo=request.POST.get('prazo') or None,
                )
        elif action == 'concluir':
            plano.estado = 'Concluído'
            plano.save()
        elif action == 'iniciar':
            plano.estado = 'Em Curso'
            plano.save()
        return redirect('rh_inst_integracao_detalhe', pk=plano.pk)
    return render(request, 'rh/institucional/recrutamento_integracao_detalhe.html',
                  _ctx_inst(request, 'recrutamento_inst', {'plano': plano, 'tarefas': tarefas}))


# ══════════════════════════════════════════════════════════════════════════
# CONTROLO DE PRESENÇAS
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presencas_view(request):
    hoje = timezone.now().date()
    mes = int(request.GET.get('mes') or hoje.month)
    ano = int(request.GET.get('ano') or hoje.year)
    from datetime import date
    primeiro_dia = date(ano, mes, 1)
    if mes == 12:
        ultimo_dia = date(ano, 12, 31)
    else:
        ultimo_dia = date(ano, mes + 1, 1) - timezone.timedelta(days=1)

    cols = ColaboradorInstitucional.objects.filter(estado='Ativo').only('id', 'nome', 'area_actuacao')
    registos = PresencaInstitucional.objects.filter(
        colaborador__in=cols, data__month=mes, data__year=ano,
    ).select_related('colaborador').order_by('-data')

    ferias_pendentes = FeriasInstitucional.objects.filter(
        colaborador__in=cols, estado='Pendente',
    ).select_related('colaborador')
    ferias_todas = FeriasInstitucional.objects.filter(
        colaborador__in=cols,
        data_inicio__lte=ultimo_dia, data_fim__gte=primeiro_dia,
    ).select_related('colaborador').order_by('-criado_em')

    paginator = Paginator(registos, 8)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'rh/institucional/presencas_lista.html',
                  _ctx_inst(request, 'presencas_inst', {
                    'colaboradores': cols, 'registos': page_obj,
                    'page_obj': page_obj, 'ferias_pendentes': ferias_pendentes,
                    'ferias_todas': ferias_todas,
                    'mes': mes, 'ano': ano, 'meses': list(enumerate(MESES, 1)), 'hoje': hoje,
                  }))


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_registar_view(request):
    if request.method == 'POST':
        col = get_object_or_404(ColaboradorInstitucional, pk=request.POST.get('colaborador'))
        try:
            data_str = request.POST.get('data')
            reg, _ = PresencaInstitucional.objects.get_or_create(colaborador=col, data=data_str)
            reg.tipo = request.POST.get('tipo', 'Entrada')
            reg.hora_entrada = request.POST.get('hora_entrada') or None
            reg.hora_saida = request.POST.get('hora_saida') or None
            reg.horas_extras = _dec(request.POST.get('horas_extras', '0'))
            reg.justificacao = request.POST.get('justificacao', '').strip()
            reg.estado = 'Pendente'
            reg.full_clean()
            reg.save()
            messages.success(request, 'Presença registada.')
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect('rh_inst_presencas')
    cols = ColaboradorInstitucional.objects.filter(estado='Ativo')
    hoje = timezone.now().date()
    tipos_presenca = getattr(PresencaInstitucional, 'TIPOS', [])
    return render(request, 'rh/institucional/presenca_registar.html',
                  _ctx_inst(request, 'presencas_inst', {
                      'colaboradores': cols, 'tipos_presenca': tipos_presenca, 'hoje': hoje,
                  }))


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_aprovar_view(request, pk):
    reg = get_object_or_404(PresencaInstitucional, pk=pk)
    if request.method == 'POST':
        reg.estado = request.POST.get('estado', 'Aprovado')
        reg.save()
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_presenca_apagar_view(request, pk):
    reg = get_object_or_404(PresencaInstitucional, pk=pk)
    if request.method == 'POST':
        reg.delete()
        messages.success(request, 'Registo removido.')
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_pedir_view(request):
    if request.method == 'POST':
        col = get_object_or_404(ColaboradorInstitucional, pk=request.POST.get('colaborador'))
        try:
            FeriasInstitucional.objects.create(
                colaborador=col,
                data_inicio=request.POST.get('data_inicio'),
                data_fim=request.POST.get('data_fim'),
                motivo=request.POST.get('motivo', '').strip(),
            )
            messages.success(request, 'Pedido de férias submetido.')
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_aprovar_view(request, pk):
    pedido = get_object_or_404(FeriasInstitucional, pk=pk)
    if request.method == 'POST':
        try:
            pedido.estado = request.POST.get('estado', 'Aprovado')
            pedido.save()
            if pedido.estado == 'Aprovado':
                marcar_ferias_no_registo_inst(pedido)
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect('rh_inst_presencas')


@_requer_inst
@_requer_inst_modulo('presencas')
def inst_ferias_apagar_view(request, pk):
    pedido = get_object_or_404(FeriasInstitucional, pk=pk)
    if request.method == 'POST':
        pedido.delete()
        messages.success(request, 'Pedido de férias removido.')
    return redirect('rh_inst_presencas')


# ══════════════════════════════════════════════════════════════════════════
# AVALIAÇÃO DE DESEMPENHO
# ══════════════════════════════════════════════════════════════════════════

@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacoes_view(request):
    ciclos = CicloAvaliacaoInstitucional.objects.annotate(
        num_avaliacoes=Count('avaliacoes')
    ).all()
    paginator = Paginator(ciclos, 8)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'rh/institucional/avaliacoes_lista.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclos': page_obj, 'page_obj': page_obj,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_ciclo_novo_view(request):
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        if nome:
            try:
                ciclo = CicloAvaliacaoInstitucional.objects.create(
                    nome=nome,
                    periodo_inicio=request.POST.get('periodo_inicio'),
                    periodo_fim=request.POST.get('periodo_fim'),
                )
                metricas_nomes = request.POST.getlist('metrica_nome[]')
                metricas_desc = request.POST.getlist('metrica_descricao[]')
                for i, mnome in enumerate(metricas_nomes):
                    mnome = mnome.strip()
                    if mnome:
                        MetricaAvaliacaoInstitucional.objects.create(
                            ciclo=ciclo, nome=mnome,
                            descricao=(metricas_desc[i] if i < len(metricas_desc) else '').strip(),
                            ordem=i,
                        )
                return redirect('rh_inst_avaliacoes')
            except ValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'Nome do ciclo é obrigatório.')
    return render(request, 'rh/institucional/avaliacao_ciclo_form.html',
                  _ctx_inst(request, 'avaliacoes_inst'))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_ciclo_detalhe_view(request, pk):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=pk)
    metricas = ciclo.metricas.all()
    avaliacoes = ciclo.avaliacoes.select_related('colaborador').prefetch_related('notas_metricas__metrica').all()
    for a in avaliacoes:
        a.notas_map = {nm.metrica_id: nm.nota for nm in a.notas_metricas.all()}
    avaliados = {a.colaborador_id for a in avaliacoes}
    pendentes = ColaboradorInstitucional.objects.filter(estado='Ativo').exclude(pk__in=avaliados)
    if not metricas:
        metricas = [
            {'nome': 'Pontualidade', 'chave': 'pontualidade'},
            {'nome': 'Produtividade', 'chave': 'produtividade'},
            {'nome': 'Qualidade do Trabalho', 'chave': 'qualidade_trabalho'},
            {'nome': 'Trabalho em Equipa', 'chave': 'trabalho_equipa'},
            {'nome': 'Iniciativa', 'chave': 'iniciativa'},
        ]
    return render(request, 'rh/institucional/avaliacao_ciclo_detalhe.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'avaliacoes': avaliacoes,
                      'metricas': metricas, 'cols_pendentes': pendentes,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_form_view(request, ciclo_pk, col_pk=None):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
    aval = col = None
    if col_pk:
        col = get_object_or_404(ColaboradorInstitucional, pk=col_pk)
        aval = AvaliacaoInstitucional.objects.filter(ciclo=ciclo, colaborador=col).first()

    if request.method == 'POST':
        col_id = col_pk or int(request.POST.get('colaborador', 0))
        col = get_object_or_404(ColaboradorInstitucional, pk=col_id)
        if not col_pk and AvaliacaoInstitucional.objects.filter(ciclo=ciclo, colaborador=col).exists():
            messages.error(request, f'{col.nome} já foi avaliado neste ciclo.')
            return redirect('rh_inst_ciclo_detalhe', pk=ciclo.pk)

        kpis = {}
        metricas = list(ciclo.metricas.all())
        for m in metricas:
            v = request.POST.get(f'metrica_{m.pk}')
            kpis[m.nome] = int(v) if v else 3
        if not metricas:
            for k in ['pontualidade', 'produtividade', 'qualidade_trabalho',
                      'trabalho_equipa', 'iniciativa']:
                v = request.POST.get(k)
                kpis[k] = int(v) if v else 3
        nota = round(sum(kpis.values()) / len(kpis), 1) if kpis else 3

        aval, created = AvaliacaoInstitucional.objects.update_or_create(
            ciclo=ciclo, colaborador=col,
            defaults={
                'nota_global': nota,
                'pontos_fortes': request.POST.get('pontos_fortes', '').strip(),
                'pontos_melhoria': request.POST.get('pontos_melhoria', '').strip(),
                'plano_desenvolvimento': request.POST.get('plano_desenvolvimento', '').strip(),
            }
        )
        if created:
            NotaMetricaInstitucional.objects.filter(avaliacao=aval).delete()
        for m in metricas:
            v = request.POST.get(f'metrica_{m.pk}')
            if v:
                NotaMetricaInstitucional.objects.create(avaliacao=aval, metrica=m, nota=int(v))

        if not metricas:
            aval.pontualidade = kpis.get('pontualidade', 3)
            aval.produtividade = kpis.get('produtividade', 3)
            aval.qualidade_trabalho = kpis.get('qualidade_trabalho', 3)
            aval.trabalho_equipa = kpis.get('trabalho_equipa', 3)
            aval.iniciativa = kpis.get('iniciativa', 3)
            aval.save(update_fields=['pontualidade', 'produtividade', 'qualidade_trabalho', 'trabalho_equipa', 'iniciativa'])
        return redirect('rh_inst_ciclo_detalhe', pk=ciclo.pk)

    cols_avaliaveis = ColaboradorInstitucional.objects.filter(estado='Ativo')
    if not col_pk:
        cols_avaliaveis = cols_avaliaveis.exclude(
            pk__in=AvaliacaoInstitucional.objects.filter(ciclo=ciclo).values_list('colaborador', flat=True)
        )

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota_obj = aval.notas_metricas.filter(metrica=m).first() if aval else None
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota_obj.nota if nota_obj else 3))
    else:
        kpis_list = [
            ('pontualidade', 'Pontualidade', '', aval.pontualidade if aval else 3),
            ('produtividade', 'Produtividade', '', aval.produtividade if aval else 3),
            ('qualidade_trabalho', 'Qualidade do Trabalho', '', aval.qualidade_trabalho if aval else 3),
            ('trabalho_equipa', 'Trabalho em Equipa', '', aval.trabalho_equipa if aval else 3),
            ('iniciativa', 'Iniciativa', '', aval.iniciativa if aval else 3),
        ]

    return render(request, 'rh/institucional/avaliacao_form.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': cols_avaliaveis, 'kpis_list': kpis_list,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_detalhe_view(request, ciclo_pk, col_pk):
    ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
    col = get_object_or_404(ColaboradorInstitucional, pk=col_pk)
    aval = get_object_or_404(AvaliacaoInstitucional, ciclo=ciclo, colaborador=col)

    metricas = ciclo.metricas.all()
    kpis_list = []
    if metricas:
        for m in metricas:
            nota_obj = aval.notas_metricas.filter(metrica=m).first()
            kpis_list.append((f'metrica_{m.pk}', m.nome, m.descricao, nota_obj.nota if nota_obj else 3, True))
    else:
        kpis_list = [
            ('pontualidade', 'Pontualidade', '', getattr(aval, 'pontualidade', 3), True),
            ('produtividade', 'Produtividade', '', getattr(aval, 'produtividade', 3), True),
            ('qualidade_trabalho', 'Qualidade do Trabalho', '', getattr(aval, 'qualidade_trabalho', 3), True),
            ('trabalho_equipa', 'Trabalho em Equipa', '', getattr(aval, 'trabalho_equipa', 3), True),
            ('iniciativa', 'Iniciativa', '', getattr(aval, 'iniciativa', 3), True),
        ]

    return render(request, 'rh/institucional/avaliacao_form.html',
                  _ctx_inst(request, 'avaliacoes_inst', {
                      'ciclo': ciclo, 'aval': aval, 'col': col,
                      'colaboradores': [], 'kpis_list': kpis_list, 'readonly': True,
                  }))


@_requer_inst
@_requer_inst_modulo('avaliacoes')
def inst_avaliacao_apagar_view(request, ciclo_pk, col_pk):
    if request.method == 'POST':
        ciclo = get_object_or_404(CicloAvaliacaoInstitucional, pk=ciclo_pk)
        aval = get_object_or_404(AvaliacaoInstitucional, ciclo=ciclo, colaborador__pk=col_pk)
        nome = aval.colaborador.nome
        aval.delete()
        messages.success(request, f'Avaliação de {nome} removida.')
    return redirect('rh_inst_ciclo_detalhe', pk=ciclo_pk)


# ══════════════════════════════════════════════════════════════════════════
# PÁGINAS PÚBLICAS (candidaturas externas)
# ══════════════════════════════════════════════════════════════════════════

def inst_vaga_publica_view(request, link_uuid):
    vaga = get_object_or_404(VagaInstitucional, link_externo=link_uuid, estado__in=['Aberta', 'Em Análise'])
    return render(request, 'rh/institucional/public/vaga_detalhe.html', {
        'vaga': vaga,
    })


def inst_candidatura_externa_view(request, link_uuid):
    vaga = get_object_or_404(VagaInstitucional, link_externo=link_uuid, estado__in=['Aberta', 'Em Análise'])
    form_data = {}
    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        telefone = request.POST.get('telefone', '').strip()
        form_data = {'nome': nome, 'email': email, 'telefone': telefone}
        if not nome or not email:
            return render(request, 'rh/institucional/public/candidatura_form.html', {
                'vaga': vaga, 'erro': 'Nome e email são obrigatórios.', 'form_data': form_data,
            })
        cv = request.FILES.get('curriculo')
        candidatura = CandidaturaInstitucional.objects.create(
            vaga=vaga, nome=nome, email=email, telefone=telefone, cv=cv,
        )
        return render(request, 'rh/institucional/public/candidatura_sucesso.html', {'vaga': vaga, 'candidatura': candidatura})
    return render(request, 'rh/institucional/public/candidatura_form.html', {'vaga': vaga, 'form_data': form_data})
