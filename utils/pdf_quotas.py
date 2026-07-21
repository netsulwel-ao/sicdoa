"""
Geração de PDFs profissionais para:
  - Certidão de Regularidade
  - Carteira Profissional

Utiliza o layout profissional do sistema (ReportLab SimpleDocTemplate + Table + Paragraph)
com cabeçalho da BancaCentral, QR Code funcional e rodapé institucional.
"""
import os
import hashlib
import uuid
import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, Image as RLImage, PageBreak,
)
from django.conf import settings

try:
    import qrcode as _qrcode
    _QRCODE_OK = True
except ImportError:
    _QRCODE_OK = False


# ── Cores institucionais ────────────────────────────────────────────────────
COR_PRIMARIO = colors.HexColor('#0f172a')
COR_SECUNDARIO = colors.white
COR_CINZA = colors.HexColor('#64748b')
COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
COR_BORDA = colors.HexColor('#cbd5e1')
COR_VERDE = colors.HexColor('#059669')
COR_VERMELHO = colors.HexColor('#dc2626')
COR_BRANCO = colors.white
COR_GOLD = colors.HexColor('#c9a84c')
COR_ALT_ROW = colors.HexColor('#f8fafc')


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    """Carrega assinatura digital da banca para ReportLab Image ou retorna None."""
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
    if not _QRCODE_OK:
        return Paragraph('', _st('empty', fontSize=1))
    try:
        _qr_buf = BytesIO()
        _qr_obj = _qrcode.QRCode(version=1, box_size=10, border=2)
        _qr_obj.add_data(texto)
        _qr_obj.make(fit=True)
        _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
        _qr_buf.seek(0)
        return RLImage(_qr_buf, width=2.2 * cm, height=2.2 * cm)
    except Exception:
        return Paragraph('', _st('empty', fontSize=1))


def _get_banca_central():
    """Retorna a BancaCentral (registo único) ou None."""
    try:
        from rh.models import BancaCentral
        return BancaCentral.get_instance()
    except Exception:
        return None


def _build_header(banca, report_name, report_subtitle, request=None):
    """Constrói o bloco de cabeçalho padrão (logo + QR + empresa + relatório)."""
    agora = datetime.datetime.now()
    story = []

    # ── Linha superior: Logo (esq) + QR Code (dir) ──
    col_logo = _carregar_logo_banca(banca)

    qr_texto = (
        f"=== {report_name.upper()} ===\n"
        f"{report_subtitle}\n"
        f"Data: {agora.strftime('%d/%m/%Y %H:%M')}"
    )
    qr_flowable = _gerar_qr_code(qr_texto)

    top_line = Table([[col_logo, qr_flowable]], colWidths=[14.5 * cm, 2.5 * cm])
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

    # ── Bloco empresa (esq) + bloco documento (dir) ──
    if banca:
        nome_txt = _safe(banca.nome) if banca.nome else 'CDOA'
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

    data_geracao = agora.strftime('%d/%m/%Y %H:%M')
    utilizador = ''
    if request and hasattr(request, 'session'):
        utilizador = request.session.get('usuario', {}).get('nome', '')

    doc_info = (
        f'<font size="9"><b>{report_name}</b></font><br/>'
        f'<font size="7.5" color="#334155">{report_subtitle}</font><br/>'
        f'<font size="7.5" color="#334155">Gerado: {data_geracao}</font>'
    )
    if utilizador:
        doc_info += f'<br/><font size="7.5" color="#334155">Utilizador: {_safe(utilizador)}</font>'

    header_body = Table([[
        Paragraph(empresa_info, _st('empresa_info', fontSize=7.5, leading=10)),
        Paragraph(doc_info, _st('doc_info', fontSize=7.5, leading=10)),
    ]], colWidths=[9.5 * cm, 7.5 * cm])
    header_body.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_body)

    # ── Linha separadora ──
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.3 * cm))

    return story


def _build_footer(story, doc_hash, codigo):
    """Constrói o rodapé padrão (hash + disclaimer)."""
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width='100%', thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.2 * cm))

    hash_text = (
        f'<font size="6.5" color="#94a3b8">'
        f'Hash SHA-256: {doc_hash[:32]}... &nbsp;|&nbsp; '
        f'Código: {codigo[:20]} &nbsp;|&nbsp; '
        f'Verifique a autenticidade no portal da CDOA.'
        f'</font>'
    )
    story.append(Paragraph(hash_text, _st('hash_footer', fontSize=6.5, textColor=COR_CINZA)))

    story.append(Spacer(1, 0.3 * cm))
    disclaimer = (
        '<font size="6.5" color="#94a3b8">'
        'CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA) — ANGOLA — '
        'Este documento é válido apenas com a assinatura digital e o selo da CDOA.'
        '</font>'
    )
    story.append(Paragraph(disclaimer, _st('disclaimer', fontSize=6.5, textColor=COR_CINZA, alignment=TA_CENTER)))


# ══════════════════════════════════════════════════════════════════════════════
# CERTIDÃO DE REGULARIDADE
# ══════════════════════════════════════════════════════════════════════════════

def gerar_certidao_pdf(despachante, admin_nome):
    """
    Gera PDF profissional da Certidão de Regularidade.
    Retorna dict com codigo, hash, validade, pdf_path, pdf_url.
    """
    banca = _get_banca_central()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title='Certidão de Regularidade',
    )

    codigo = str(uuid.uuid4()).upper()
    validade_date = datetime.date.today() + datetime.timedelta(days=90)
    validade = validade_date.isoformat()
    hoje = datetime.date.today()
    data_emissao = hoje.strftime('%d de %B de %Y')

    # Hash de segurança
    raw = f'{codigo}-{despachante.id}-{datetime.datetime.now().isoformat()}'
    cert_hash = hashlib.sha256(raw.encode()).hexdigest()

    story = []

    # ── Cabeçalho institucional ──
    story.extend(_build_header(
        banca,
        'CERTIDÃO DE REGULARIDADE',
        'Situação Financeira e Disciplinar',
    ))

    # ── Código de registo ──
    story.append(Paragraph(
        f'<font size="8" color="#64748b">Registo Nº {codigo[:20]}</font>',
        _st('registo', fontSize=8, textColor=COR_CINZA)
    ))
    story.append(Spacer(1, 0.4 * cm))

    # ── Texto principal ──
    story.append(Paragraph(
        'A CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA), no uso das suas '
        'atribuições legais e estatutárias, vem por meio desta '
        '<b>CERTIDÃO DE REGULARIDADE</b> declarar que:',
        _st('texto1', fontSize=10, leading=14)
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── Nome do despachante em destaque ──
    nome_box_data = [[
        Paragraph(
            f'<font size="14" color="#0f172a"><b>{_safe(despachante.nome.upper())}</b></font>',
            _st('nome_desp', fontSize=14, textColor=COR_PRIMARIO)
        )
    ]]
    nome_box = Table(nome_box_data, colWidths=[16 * cm])
    nome_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_CINZA_CLARO),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(nome_box)
    story.append(Spacer(1, 0.3 * cm))

    # ── Dados do despachante ──
    dados_data = [
        ['Cédula Profissional', despachante.cedula or '—'],
        ['NIF', despachante.nif or '—'],
        ['Data de Emissão', data_emissao],
        ['Validade', f'{validade_date.strftime("%d/%m/%Y")} (90 dias)'],
    ]
    dados_rows = []
    for label, valor in dados_data:
        dados_rows.append([
            Paragraph(f'<b>{label}</b>', _st('label', fontSize=9, textColor=COR_CINZA)),
            Paragraph(str(valor), _st('valor', fontSize=9, textColor=COR_PRIMARIO)),
        ])

    dados_table = Table(dados_rows, colWidths=[5 * cm, 11 * cm])
    dados_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, COR_BORDA),
    ]))
    story.append(dados_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Declaração ──
    story.append(Paragraph(
        'encontra-se em situação <b>REGULAR</b> perante esta Câmara, não possuindo '
        'quaisquer débitos ou pendências financeiras ou disciplinares até à presente data.',
        _st('declaracao', fontSize=10, leading=14)
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── Data e local ──
    story.append(Paragraph(
        f'Luanda, {data_emissao}',
        _st('data_local', fontSize=10, alignment=TA_RIGHT)
    ))
    story.append(Spacer(1, 1.0 * cm))

    # ── Assinaturas ──
    assinatura_img = _carregar_assinatura_banca(banca)

    assinatura_data = [
        [
            Paragraph('O Presidente da CDOA', _st('sig_label', fontSize=8, textColor=COR_CINZA, alignment=TA_CENTER)),
        ],
    ]
    if assinatura_img:
        assinatura_data.append([
            assinatura_img,
        ])
    assinatura_data.append([
        Paragraph('(Assinatura e Carimbo)', _st('sig_sub', fontSize=7, textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)),
    ])
    assinatura_table = Table(assinatura_data, colWidths=[16 * cm])
    assinatura_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(assinatura_table)

    # ── Rodapé ──
    _build_footer(story, cert_hash, codigo)

    # ── Gerar PDF ──
    doc.build(story)

    pdf_path = os.path.join(settings.MEDIA_ROOT, 'certidoes', f'{codigo}.pdf')
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(buffer.getvalue())

    return {
        'codigo': codigo,
        'hash': cert_hash,
        'validade': validade,
        'pdf_path': f'certidoes/{codigo}.pdf',
        'pdf_url': f'/media/certidoes/{codigo}.pdf',
    }


# ══════════════════════════════════════════════════════════════════════════════
# CARTEIRA PROFISSIONAL
# ══════════════════════════════════════════════════════════════════════════════

def gerar_carteira_pdf(despachante, carteira, admin_nome='Administração CDOA'):
    """
    Gera PDF profissional da Carteira Profissional.
    Retorna (pdf_filename, pdf_url).
    """
    banca = _get_banca_central()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title='Carteira Profissional',
    )

    hoje = datetime.date.today()
    codigo_doc = str(uuid.uuid4()).upper()[:16]

    # Hash de segurança
    raw = f'{carteira.numero_carteira}-{despachante.id}-{datetime.datetime.now().isoformat()}'
    doc_hash = hashlib.sha256(raw.encode()).hexdigest()

    # QR Code com dados de validação
    qr_data = f"CDOA:{carteira.numero_carteira}|{despachante.nome}|{despachante.cedula or ''}"

    story = []

    # ── Cabeçalho institucional ──
    story.extend(_build_header(
        banca,
        'CARTEIRA PROFISSIONAL',
        'Documento de Identificação do Despachante Oficial',
    ))

    # ── Número e validade em destaque ──
    num_validade_data = [[
        Paragraph(
            f'<font size="8" color="#94a3b8">Nº DA CARTEIRA</font><br/>'
            f'<font size="16" color="#ffffff"><b>{_safe(carteira.numero_carteira)}</b></font>',
            _st('num_cart', fontSize=16, textColor=COR_BRANCO)
        ),
        Paragraph(
            f'<font size="8" color="#94a3b8">VALIDADE</font><br/>'
            f'<font size="14" color="#ffffff"><b>{carteira.data_validade.strftime("%d/%m/%Y")}</b></font>',
            _st('validade_cart', fontSize=14, textColor=COR_BRANCO, alignment=TA_RIGHT)
        ),
    ]]
    num_validade_box = Table(num_validade_data, colWidths=[10 * cm, 6 * cm])
    num_validade_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_PRIMARIO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(num_validade_box)
    story.append(Spacer(1, 0.5 * cm))

    # ── Dados do despachante ──
    dados_items = [
        ('NOME COMPLETO', despachante.nome.upper()),
        ('CÉDULA PROFISSIONAL', despachante.cedula or '—'),
        ('NIF', despachante.nif or '—'),
        ('EMAIL', despachante.email or '—'),
        ('TELEFONE', despachante.telefone or '—'),
        ('CATEGORIA', 'Despachante Oficial'),
        ('ESTADO', carteira.status.upper()),
    ]

    dados_rows = []
    for label, valor in dados_items:
        dados_rows.append([
            Paragraph(
                f'<font size="8" color="#64748b">{label}</font>',
                _st(f'l_{label}', fontSize=8, textColor=COR_CINZA)
            ),
            Paragraph(
                f'<font size="10" color="#0f172a"><b>{_safe(str(valor))}</b></font>',
                _st(f'v_{label}', fontSize=10, textColor=COR_PRIMARIO)
            ),
        ])

    # Verificar se despachante tem foto
    foto_path = None
    if despachante.foto:
        from django.conf import settings
        caminho_foto = os.path.join(settings.MEDIA_ROOT, str(despachante.foto))
        if os.path.exists(caminho_foto):
            foto_path = caminho_foto

    if foto_path:
        from reportlab.lib.utils import ImageReader
        dados_table = Table(dados_rows, colWidths=[4.5 * cm, 9.5 * cm, 3 * cm])
        try:
            img = ImageReader(foto_path)
            dados_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, COR_BORDA),
                ('BACKGROUND', (0, 0), (-1, 0), COR_CINZA_CLARO),
                ('SPAN', (2, 0), (2, -1)),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('VALIGN', (2, 0), (2, -1), 'MIDDLE'),
            ]))
            from reportlab.platypus import Image as RLImage
            foto_img = RLImage(foto_path, width=2.5 * cm, height=3 * cm, kind='proportional')
            dados_rows[0].append(foto_img)
        except Exception:
            dados_table = Table(dados_rows, colWidths=[5 * cm, 11 * cm])
            dados_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LINEBELOW', (0, 0), (-1, -2), 0.5, COR_BORDA),
                ('BACKGROUND', (0, 0), (-1, 0), COR_CINZA_CLARO),
            ]))
    else:
        dados_table = Table(dados_rows, colWidths=[5 * cm, 11 * cm])
        dados_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, COR_BORDA),
            ('BACKGROUND', (0, 0), (-1, 0), COR_CINZA_CLARO),
        ]))

    story.append(dados_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Data de emissão e renovação ──
    emissor_data = [
        [
            Paragraph(
                f'<font size="8" color="#64748b">DATA DE EMISSÃO</font><br/>'
                f'<font size="10" color="#0f172a"><b>{carteira.data_emissao.strftime("%d/%m/%Y")}</b></font>',
                _st('emissao', fontSize=10)
            ),
            Paragraph(
                f'<font size="8" color="#64748b">DATA DE RENOVAÇÃO</font><br/>'
                f'<font size="10" color="#0f172a"><b>{carteira.data_renovacao.strftime("%d/%m/%Y") if carteira.data_renovacao else "—"}</b></font>',
                _st('renovacao', fontSize=10)
            ),
            Paragraph(
                f'<font size="8" color="#64748b">EMITIDO POR</font><br/>'
                f'<font size="10" color="#0f172a"><b>{_safe(admin_nome)}</b></font>',
                _st('emissor', fontSize=10)
            ),
        ]
    ]
    emissor_table = Table(emissor_data, colWidths=[5.3 * cm, 5.3 * cm, 5.4 * cm])
    emissor_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('LINEBEFORE', (1, 0), (1, 0), 0.5, COR_BORDA),
        ('BACKGROUND', (0, 0), (-1, -1), COR_CINZA_CLARO),
    ]))
    story.append(emissor_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Assinatura ──
    assinatura_img = _carregar_assinatura_banca(banca)
    if assinatura_img:
        assinatura_data = [[
            Paragraph('O Presidente da CDOA', _st('sig_label_cart', fontSize=8, textColor=COR_CINZA, alignment=TA_CENTER)),
        ], [
            assinatura_img,
        ], [
            Paragraph('(Assinatura e Carimbo)', _st('sig_sub_cart', fontSize=7, textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)),
        ]]
        assinatura_table = Table(assinatura_data, colWidths=[16 * cm])
        assinatura_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(assinatura_table)
        story.append(Spacer(1, 0.5 * cm))

    # ── QR Code + Texto legal ──
    qr_img = _gerar_qr_code(qr_data)

    legal_texto = (
        '<font size="7.5" color="#64748b">'
        'A presente Carteira Profissional é o documento de identificação do Despachante Oficial '
        'devidamente habilitado a exercer a actividade de despachante aduaneiro em território nacional, '
        'ao abrigo do Estatuto da CDOA e demais legislação aplicável.'
        '<br/><br/>'
        f'<b>Código de Verificação:</b> {codigo_doc}<br/>'
        f'<b>Hash SHA-256:</b> {doc_hash[:32]}...<br/>'
        'Para validar a autenticidade, acede ao portal da CDOA e introduza o código acima.'
        '</font>'
    )

    qr_legal_data = [[
        qr_img,
        Paragraph(legal_texto, _st('legal', fontSize=7.5, leading=10, textColor=COR_CINZA)),
    ]]
    qr_legal_table = Table(qr_legal_data, colWidths=[3 * cm, 13 * cm])
    qr_legal_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(qr_legal_table)

    # ── Rodapé ──
    _build_footer(story, doc_hash, carteira.numero_carteira)

    # ── Gerar PDF ──
    doc.build(story)

    safe_number = carteira.numero_carteira.replace("/", "-").replace("\\", "-")
    pdf_filename = f'carteiras/{safe_number}.pdf'
    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_filename)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(buffer.getvalue())

    return pdf_filename, f'/media/{pdf_filename}'
