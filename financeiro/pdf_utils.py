"""
Utilitário para geração de PDFs de relatórios financeiros.
Segue o padrão profissional da Requisição de Fundos (CDOA/NETSULWEL).
"""
import io
import hashlib
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, Image as RLImage, PageBreak,
)

from utils.format_kz import fmt_kz


# ── Cores padrão CDOA ──────────────────────────────────────────────────────
COR_PRIMARIO = colors.HexColor('#0f172a')
COR_SECUNDARIO = colors.white
COR_CINZA = colors.HexColor('#64748b')
COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
COR_BORDA = colors.HexColor('#cbd5e1')
COR_VERDE = colors.HexColor('#059669')
COR_VERMELHO = colors.HexColor('#dc2626')
COR_BRANCO = colors.white
COR_HEADER = colors.white
COR_HEADER_BG = colors.HexColor('#0f172a')
COR_ALT_ROW = colors.HexColor('#f8fafc')


def _safe(text):
    """Escapa caracteres HTML/XML para ReportLab Paragraph."""
    if not text:
        return ''
    from django.utils.html import escape as _esc
    return _esc(str(text))


def _st(name, **kw):
    """Cria ParagraphStyle padrão."""
    defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRIMARIO, leading=11)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


def _hash_documento(dados):
    """Gera hash curto do documento para rodapé."""
    raw = '|'.join(str(v) for v in dados)
    return hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _carregar_logo_banca(banca):
    """Carrega logo da banca para ReportLab Image ou retorna Paragraph vazio."""
    if not banca:
        return Paragraph('', _st('empty', fontSize=1))
    logo_path = None
    if hasattr(banca, 'logo') and banca.logo:
        try:
            logo_path = banca.logo.path
        except Exception:
            pass
    if logo_path:
        try:
            return RLImage(logo_path, width=2.4 * cm, height=1.7 * cm)
        except Exception:
            pass
    return Paragraph('', _st('empty', fontSize=1))


def _carregar_assinatura_banca(banca):
    """Carrega assinatura digital da banca para ReportLab Image ou retorna Paragraph vazio."""
    if not banca:
        return None
    assinatura_path = None
    if hasattr(banca, 'assinatura') and banca.assinatura:
        try:
            assinatura_path = banca.assinatura.path
        except Exception:
            pass
    if assinatura_path:
        try:
            return RLImage(assinatura_path, width=4 * cm, height=1.5 * cm)
        except Exception:
            pass
    return None


def _gerar_qr_code(texto):
    """Gera QR Code como ReportLab Image."""
    import qrcode as _qr
    import io
    _qr_buf = io.BytesIO()
    _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
    _qr_obj.add_data(texto)
    _qr_obj.make(fit=True)
    _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
    _qr_buf.seek(0)
    return RLImage(_qr_buf, width=1.9 * cm, height=1.9 * cm)


def _valor_por_extenso(valor):
    """Converte valor numérico para extenso em português (simplificado)."""
    try:
        valor = Decimal(str(valor))
    except Exception:
        return ''
    if valor == 0:
        return 'Zero Kwanzas'

    unidades = ['', 'Um', 'Dois', 'Três', 'Quatro', 'Cinco', 'Seis', 'Sete', 'Oito', 'Nove']
    dezenas = ['', 'Dez', 'Vinte', 'Trinta', 'Quarenta', 'Cinquenta', 'Sessenta', 'Setenta', 'Oitenta', 'Noventa']
    especiais = {'10': 'Dez', '11': 'Onze', '12': 'Doze', '13': 'Treze', '14': 'Quatorze',
                 '15': 'Quinze', '16': 'Dezesseis', '17': 'Dezessete', '18': 'Dezoito', '19': 'Dezenove'}
    centenas = ['', 'Cento', 'Duzentos', 'Trezentos', 'Quatrocentos', 'Quinhentos',
                'Seiscentos', 'Setecentos', 'Oitocentos', 'Novecentos']

    def _bloco(n):
        if n == 0:
            return ''
        if n == 100:
            return 'Cem'
        partes = []
        c = n // 100
        d = (n % 100) // 10
        u = n % 10
        if c > 0:
            partes.append(centenas[c])
        r = n % 100
        if r >= 10 and r < 20:
            partes.append(especiais[str(r)])
        else:
            if d > 0:
                partes.append(dezenas[d])
            if u > 0:
                partes.append(unidades[u])
        return ' e '.join(partes)

    inteiro = int(valor)
    dec = int((valor - inteiro) * 100)

    if inteiro == 0:
        resultado = 'Zero'
    else:
        partes = []
        milhoes = inteiro // 1_000_000
        milhares = (inteiro % 1_000_000) // 1_000
        restante = inteiro % 1_000
        if milhoes > 0:
            if milhoes == 1:
                partes.append('Um Milhão')
            else:
                partes.append(f'{_bloco(milhoes)} Milhões')
        if milhares > 0:
            if milhares == 1:
                partes.append('Mil')
            else:
                partes.append(f'{_bloco(milhares)} Mil')
        if restante > 0:
            partes.append(_bloco(restante))
        resultado = ' e '.join(partes)

    resultado += ' Kwanzas'
    if dec > 0:
        resultado += f' e {dec:02d} centavos'
    return resultado


def gerar_pdf_relatorio(
    report_name,
    report_subtitle,
    columns,
    rows,
    summary_cards=None,
    extra_tables=None,
    filtros=None,
    banca=None,
    titulo_documento=None,
    notas=None,
    request=None,
    landscape_mode=True,
):
    """
    Gera PDF profissional para relatórios financeiros.
    
    Parâmetros:
        report_name: Nome do relatório (ex: "Relatório de Facturação")
        report_subtitle: Subtítulo (ex: "Resumo de todas as facturas emitidas")
        columns: Lista de strings com nomes das colunas
        rows: Lista de dicts {'cells': [str, ...], 'values': [Decimal, ...]}
              'cells' é o que aparece no PDF, 'values' é opcional para totais
        summary_cards: Lista de dicts {'label': str, 'value': str, 'color': str}
        extra_tables: Lista de dicts {'title': str, 'columns': [str], 'rows': [{'cells': [str]}]}
        filtros: Dict com filtros aplicados {'periodo': str, 'estado': str, ...}
        banca: Objeto Banca para logo (opcional)
        titulo_documento: Título alternativo (opcional)
        notas: Texto de nota explicativa (opcional)
        request: HttpRequest para dados do utilizador (opcional)
        landscape_mode: Se True, usa A4 landscape (padrão: True)
    
    Retorna:
        bytes do PDF
    """
    buffer = io.BytesIO()

    if landscape_mode:
        PAGE_W, PAGE_H = landscape(A4)
    else:
        PAGE_W, PAGE_H = A4

    MARGIN = 0.7 * cm
    W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4) if landscape_mode else A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title=report_name,
    )

    agora = datetime.now()
    story = []

    # ════════════════════════════════════════════════════════════════
    # 1. HEADER: LOGO (esq) + QR CODE (dir)
    # ════════════════════════════════════════════════════════════════
    col_logo = _carregar_logo_banca(banca)

    qr_texto = (
        f"=== {report_name.upper()} ===\n"
        f"{report_subtitle}\n"
        f"Data: {agora.strftime('%d/%m/%Y %H:%M')}\n"
        f"Registos: {len(rows)}"
    )
    qr_flowable = _gerar_qr_code(qr_texto)

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

    # ════════════════════════════════════════════════════════════════
    # 2. BLOCO EMPRESA (esq) + BLOCO RELATÓRIO (dir)
    # ════════════════════════════════════════════════════════════════
    if banca:
        nome_txt = _safe(banca.nome) if banca.nome else 'Despachante Oficial'
        nif_txt = banca.nif or 'N/D'
        cdoa = _safe(getattr(banca, 'licenca_cdoa', '') or '') or '—'
        endereco = _safe(banca.endereco) or '—'
        telefone = _safe(banca.telefone) or '—'
        email_b = _safe(banca.email) or '—'
    else:
        nome_txt = 'Câmara dos Despachantes Oficiais de Angola'
        nif_txt = '5417276825'
        cdoa = '—'
        endereco = '—'
        telefone = '—'
        email_b = '—'

    empresa_info = (
        f'<font size="9"><b>{nome_txt}</b></font><br/>'
        f'<font size="7.5" color="#334155">Residência: {endereco}</font><br/>'
        f'<font size="7.5" color="#334155">Tel: {telefone}</font><br/>'
        f'<font size="7.5" color="#334155">Email: {email_b}</font><br/>'
        f'<font size="7.5" color="#334155">NIF: {nif_txt} &nbsp;|&nbsp; Licença CDOA: {cdoa}</font>'
    )

    periodo = filtros.get('periodo', '') if filtros else ''
    data_geracao = agora.strftime('%d/%m/%Y %H:%M')
    utilizador = ''
    if request and hasattr(request, 'session'):
        utilizador = request.session.get('usuario', {}).get('nome', '')

    relatorio_info = (
        f'<font size="9"><b>{report_name}</b></font><br/>'
        f'<font size="7.5" color="#334155">{report_subtitle}</font><br/>'
    )
    if periodo:
        relatorio_info += f'<font size="7.5" color="#334155">Período: {periodo}</font><br/>'
    relatorio_info += f'<font size="7.5" color="#334155">Gerado: {data_geracao}</font>'
    if utilizador:
        relatorio_info += f'<br/><font size="7.5" color="#334155">Utilizador: {_safe(utilizador)}</font>'

    header_body = Table([[
        Paragraph(empresa_info, _st('empresa_info', fontSize=7.5, leading=10)),
        Paragraph(relatorio_info, _st('relatorio_info', fontSize=7.5, leading=10)),
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

    # ════════════════════════════════════════════════════════════════
    # 3. TÍTULO DO DOCUMENTO
    # ════════════════════════════════════════════════════════════════
    titulo = titulo_documento or report_name
    story.append(Paragraph(
        f'<font size="12"><b>{_safe(titulo)}</b></font>',
        _st('titulo', fontSize=12)
    ))
    story.append(Spacer(1, 0.15 * cm))

    # ════════════════════════════════════════════════════════════════
    # 4. DADOS DO DOCUMENTO (filtros aplicados)
    # ════════════════════════════════════════════════════════════════
    if filtros:
        filtro_items = []
        filtro_valores = []
        for chave, valor in filtros.items():
            if valor:
                filtro_items.append(Paragraph(f'<b>{_safe(chave.title())}</b>', _st('fi', fontSize=7.5)))
                filtro_valores.append(Paragraph(_safe(str(valor)), _st('fv', fontSize=7.5)))
        if filtro_items:
            # Dividir em colunas (máx 5 por linha)
            num_cols = min(len(filtro_items), 5)
            t_filtro_header = filtro_items[:num_cols]
            t_filtro_valores = filtro_valores[:num_cols]
            col_w = W / num_cols
            t_filtro = Table([t_filtro_header, t_filtro_valores], colWidths=[col_w] * num_cols)
            t_filtro.setStyle(TableStyle([
                ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_CINZA),
                ('LINEBELOW', (0, 1), (-1, 1), 0.5, COR_CINZA),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(t_filtro)
            story.append(Spacer(1, 0.2 * cm))

    # ════════════════════════════════════════════════════════════════
    # 5. SUMMARY CARDS (KPIs)
    # ════════════════════════════════════════════════════════════════
    if summary_cards:
        cards_header = []
        cards_valores = []
        cards_subtitulos = []
        num_cards = len(summary_cards)
        card_width = W / num_cards

        color_map = {
            'primary': '#0f172a',
            'success': '#059669',
            'danger': '#dc2626',
            'warning': '#d97706',
        }

        for card in summary_cards:
            cor = color_map.get(card.get('color', ''), '#0f172a')
            cards_header.append(Paragraph(
                f'<font size="7" color="#64748b">{_safe(card["label"])}</font>',
                _st('ch', fontSize=7)
            ))
            cards_valores.append(Paragraph(
                f'<font size="12" color="{cor}"><b>{_safe(str(card["value"]))}</b></font>',
                _st('cv', fontSize=12)
            ))

        t_cards = Table([cards_header, cards_valores], colWidths=[card_width] * num_cards)
        t_cards.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), COR_CINZA_CLARO),
            ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
            ('LINEBEFORE', (1, 0), (1, 0), 0.3, COR_BORDA) if num_cards > 1 else ('LINEBEFORE', (0, 0), (-1, -1), 0, COR_BRANCO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(t_cards)
        story.append(Spacer(1, 0.3 * cm))

    # ════════════════════════════════════════════════════════════════
    # 6. TABELA DE DADOS PRINCIPAL
    # ════════════════════════════════════════════════════════════════
    if columns and rows:
        num_cols = len(columns)
        col_widths = [W / num_cols] * num_cols

        # Headers
        table_data = [[
            Paragraph(f'<b>{_safe(col)}</b>', _st(f'h_{i}', fontSize=7.5, textColor=COR_PRIMARIO))
            for i, col in enumerate(columns)
        ]]

        # Rows
        for row in rows:
            cells = row.get('cells', row) if isinstance(row, dict) else row
            table_data.append([
                Paragraph(_safe(str(cell)), _st(f'c_{id(row)}_{i}', fontSize=7))
                for i, cell in enumerate(cells)
            ])

        t_dados = Table(table_data, colWidths=col_widths)
        style_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]
        # Linhas alternadas
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_cmds.append(('BACKGROUND', (0, i), (-1, i), COR_ALT_ROW))
        t_dados.setStyle(TableStyle(style_cmds))
        story.append(t_dados)
        story.append(Spacer(1, 0.2 * cm))

    # ════════════════════════════════════════════════════════════════
    # 7. EXTRA TABLES (tabelas adicionais)
    # ════════════════════════════════════════════════════════════════
    if extra_tables:
        for tbl_data in extra_tables:
            # Título da tabela
            story.append(Paragraph(
                f'<font size="8"><b>{_safe(tbl_data.get("title", ""))}</b></font>',
                _st('et_title', fontSize=8)
            ))
            story.append(Spacer(1, 0.1 * cm))

            tbl_cols = tbl_data.get('columns', [])
            tbl_rows = tbl_data.get('rows', [])
            if tbl_cols:
                num_cols = len(tbl_cols)
                col_widths = [W / num_cols] * num_cols

                table_data = [[
                    Paragraph(f'<b>{_safe(col)}</b>', _st(f'eth_{i}', fontSize=7.5, textColor=COR_PRIMARIO))
                    for i, col in enumerate(tbl_cols)
                ]]
                for row in tbl_rows:
                    cells = row.get('cells', row) if isinstance(row, dict) else row
                    table_data.append([
                        Paragraph(_safe(str(cell)), _st(f'etc_{id(row)}_{i}', fontSize=7))
                        for i, cell in enumerate(cells)
                    ])

                t_extra = Table(table_data, colWidths=col_widths)
                t_extra.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
                    ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
                    ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(t_extra)
                story.append(Spacer(1, 0.2 * cm))

    # ════════════════════════════════════════════════════════════════
    # 8. NOTA EXPLICATIVA
    # ════════════════════════════════════════════════════════════════
    if notas:
        nota_box = Table([[
            Paragraph('<b>Nota</b>', _st('nota_h', fontSize=7.5, textColor=COR_PRIMARIO)),
        ]], colWidths=[W])
        nota_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_SECUNDARIO),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, 0), 6),
        ]))
        story.append(nota_box)
        story.append(Paragraph(
            _safe(notas),
            _st('nota_txt', fontSize=7, textColor=COR_SECUNDARIO)
        ))
        story.append(Spacer(1, 0.15 * cm))

    # ════════════════════════════════════════════════════════════════
    # 9. ASSINATURA DIGITAL (se disponível)
    # ════════════════════════════════════════════════════════════════
    _assinatura_img = _carregar_assinatura_banca(banca)
    if _assinatura_img:
        story.append(Spacer(1, 0.15 * cm))
        story.append(_assinatura_img)
        story.append(Spacer(1, 0.1 * cm))

    # ════════════════════════════════════════════════════════════════
    # 10. RODAPÉ: HASH + PÁGINA/DATA
    # ════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor('#e2e2e2')))
    story.append(Spacer(1, 0.1 * cm))

    hash_dados = [report_name, data_geracao, str(len(rows))]
    doc_hash = _hash_documento(hash_dados)

    footer_text = (
        f'<font size="6" color="#94a3b8"><b>{_safe(nome_txt)} - HASH: {doc_hash}</b> &nbsp;|&nbsp; '
        f'Processado por programa válido nº35/AGT/2019<br/>'
        f'Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>'
    )
    story.append(Paragraph(footer_text, _st('footer', fontSize=6)))

    # BUILD DO PDF
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
