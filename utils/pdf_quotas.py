import os
import hashlib
import uuid
import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white, navy
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Table, TableStyle, Paragraph
from django.conf import settings

CDOA_BLUE = HexColor('#1a3a5c')
CDOA_GOLD = HexColor('#c9a84c')
CDOA_RED = HexColor('#8b0000')
GRAY_LIGHT = HexColor('#f0f0f0')

def _draw_border(c, x, y, w, h):
    c.setStrokeColor(CDOA_BLUE)
    c.setLineWidth(2)
    c.rect(x, y, w, h)
    c.setStrokeColor(CDOA_GOLD)
    c.setLineWidth(0.5)
    c.rect(x + 4, y + 4, w - 8, h - 8)

def _draw_header(c, title, subtitle=''):
    c.saveState()
    c.setFillColor(CDOA_BLUE)
    c.rect(0, A4[1] - 50, A4[0], 50, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(30, A4[1] - 35, 'REPÚBLICA DE ANGOLA')
    c.setFont('Helvetica', 9)
    c.drawString(30, A4[1] - 20, 'CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)')
    c.setFillColor(CDOA_GOLD)
    c.setFont('Helvetica-Bold', 22)
    c.drawCentredString(A4[0] / 2, A4[1] - 85, title)
    if subtitle:
        c.setFillColor(HexColor('#555555'))
        c.setFont('Helvetica', 10)
        c.drawCentredString(A4[0] / 2, A4[1] - 100, subtitle)
    c.restoreState()

def _draw_footer(c):
    c.saveState()
    c.setStrokeColor(CDOA_GOLD)
    c.setLineWidth(0.5)
    c.line(30, 55, A4[0] - 30, 55)
    c.setFont('Helvetica', 7)
    c.setFillColor(HexColor('#888888'))
    c.drawCentredString(A4[0] / 2, 40, 'CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA) — ANGOLA')
    c.drawCentredString(A4[0] / 2, 28, 'Este documento é válido apenas com a assinatura digital e selo da CDOA.')
    c.restoreState()

def gerar_certidao_pdf(despachante, admin_nome):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Fundo
    c.saveState()
    c.setFillColor(HexColor('#fafaf5'))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.restoreState()

    _draw_border(c, 15, 15, w - 30, h - 30)
    _draw_header(c, 'CERTIDÃO DE REGULARIDADE', 'Situação Financeira e Disciplinar')

    codigo = str(uuid.uuid4()).upper()
    validade = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    hoje = datetime.date.today().strftime('%d de %B de %Y')

    # Número de registro
    c.saveState()
    c.setFont('Courier-Bold', 10)
    c.setFillColor(HexColor('#666666'))
    c.drawString(40, h - 120, f'Registo Nº {codigo[:16]}')
    c.restoreState()

    # Texto principal
    y = h - 155
    c.saveState()
    c.setFont('Helvetica', 11)
    c.setFillColor(HexColor('#333333'))

    linhas = [
        f'A CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA), no uso das suas atribuições legais e',
        f'estatutárias, vem por meio desta CERTIDÃO DE REGULARIDADE declarar que:',
        '',
    ]
    for linha in linhas:
        c.drawString(40, y, linha)
        y -= 16

    # Nome do despachante em destaque
    y -= 4
    c.setFillColor(CDOA_BLUE)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(40, y, despachante.nome.upper())
    y -= 22
    c.setFillColor(HexColor('#333333'))
    c.setFont('Helvetica', 11)
    info = f'Cédula Profissional Nº {despachante.cedula or "__________"} | NIF: {despachante.nif or "__________"}'
    c.drawString(40, y, info)
    y -= 30

    c.drawString(40, y, 'encontra-se em situação REGULAR perante esta Câmara, não possuindo quaisquer')
    y -= 16
    c.drawString(40, y, 'débitos ou pendências financeiras ou disciplinares até à presente data.')
    y -= 30

    c.setFont('Helvetica-Bold', 11)
    c.drawString(40, y, 'Validade:')
    c.setFont('Helvetica', 11)
    c.drawString(110, y, f'{validade} (90 dias a contar da data de emissão)')
    y -= 20
    c.setFont('Helvetica-Bold', 11)
    c.drawString(40, y, 'Data de Emissão:')
    c.setFont('Helvetica', 11)
    c.drawString(170, y, hoje)
    c.restoreState()

    # Hash de segurança
    raw = f'{codigo}-{despachante.id}-{datetime.datetime.now().isoformat()}'
    cert_hash = hashlib.sha256(raw.encode()).hexdigest()
    c.saveState()
    y = h - 380
    c.setFillColor(HexColor('#f8f8f8'))
    c.rect(40, y - 5, w - 80, 55, fill=1, stroke=0)
    c.setStrokeColor(HexColor('#dddddd'))
    c.rect(40, y - 5, w - 80, 55, fill=0, stroke=1)
    c.setFont('Courier', 7)
    c.setFillColor(HexColor('#888888'))
    c.drawString(50, y + 5, f'Hash SHA-256: {cert_hash[:64]}')
    c.drawString(50, y - 10, f'Código de Verificação: {codigo[:24]}')
    c.drawString(50, y - 25, 'Para validar a autenticidade, aceda ao portal da CDOA e introduza o código acima.')
    c.restoreState()

    # Assinaturas
    y = h - 480
    c.saveState()
    c.setStrokeColor(HexColor('#999999'))
    c.setLineWidth(1)
    mid = w / 2
    c.line(80, y, mid - 40, y)
    c.line(mid + 40, y, w - 80, y)
    c.setFont('Helvetica', 9)
    c.setFillColor(HexColor('#555555'))
    c.drawCentredString((80 + mid - 40) / 2, y - 15, 'O Presidente da CDOA')
    c.drawCentredString((mid + 40 + w - 80) / 2, y - 15, 'O Secretário-Geral')
    c.setFont('Helvetica', 7)
    c.setFillColor(HexColor('#999999'))
    c.drawCentredString((80 + mid - 40) / 2, y - 28, '(Assinatura e Carimbo)')
    c.drawCentredString((mid + 40 + w - 80) / 2, y - 28, '(Assinatura e Carimbo)')
    c.restoreState()

    # Selo dourado (círculo decorativo)
    c.saveState()
    c.setStrokeColor(CDOA_GOLD)
    c.setLineWidth(3)
    cx, cy = w - 80, h - 150
    c.circle(cx, cy, 20)
    c.setFillColor(CDOA_GOLD)
    c.setFont('Helvetica-Bold', 10)
    c.drawCentredString(cx, cy - 4, 'CDOA')
    c.restoreState()

    # Número de página
    c.saveState()
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#aaaaaa'))
    c.drawCentredString(w / 2, 16, f'Documento gerado electronicamente • {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")} • Pág. 1/1')
    c.restoreState()

    _draw_footer(c)
    c.showPage()
    c.save()

    pdf_path = os.path.join(settings.MEDIA_ROOT, 'certidoes', f'{codigo}.pdf')
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(buf.getvalue())

    return {
        'codigo': codigo,
        'hash': cert_hash,
        'validade': validade,
        'pdf_path': f'certidoes/{codigo}.pdf',
        'pdf_url': f'/media/certidoes/{codigo}.pdf',
    }


def gerar_carteira_pdf(despachante, carteira, admin_nome='Administração CDOA'):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # Fundo
    c.saveState()
    c.setFillColor(HexColor('#fafaf5'))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.restoreState()

    _draw_border(c, 15, 15, w - 30, h - 30)
    _draw_header(c, 'CARTEIRA PROFISSIONAL', 'Documento de Identificação do Despachante')

    hoje = datetime.date.today()
    codigo_doc = str(uuid.uuid4()).upper()[:16]

    # Faixa lateral com a foto (simulada)
    c.saveState()
    c.setFillColor(CDOA_BLUE)
    c.rect(35, 125, 120, 160, fill=1, stroke=0)
    c.setFillColor(HexColor('#2a5a8c'))
    c.rect(38, 128, 114, 154, fill=1, stroke=0)
    # Placeholder para foto
    c.setFillColor(HexColor('#4a7aaa'))
    c.circle(95, 210, 40)
    c.setFillColor(white)
    c.setFont('Helvetica', 40)
    c.drawCentredString(95, 198, '👤')
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#cccccc'))
    c.drawCentredString(95, 165, 'FOTO')
    c.setFont('Helvetica-Bold', 11)
    c.setFillColor(white)
    c.drawCentredString(95, 140, 'CDOA')
    c.restoreState()

    # Dados do membro
    x = 170
    y_dados = h - 150
    c.saveState()
    c.setFont('Helvetica-Bold', 9)
    c.setFillColor(HexColor('#888888'))
    labels = ['NOME COMPLETO', 'CÉDULA PROFISSIONAL', 'NIF', 'EMAIL', 'TELEFONE', 'CATEGORIA', 'ESTADO']
    vals = [
        despachante.nome.upper(),
        (despachante.cedula or '__________'),
        (despachante.nif or '__________'),
        (despachante.email or '__________'),
        (despachante.telefone or '__________'),
        'Despachante Oficial',
        carteira.status.upper(),
    ]
    for i, (label, val) in enumerate(zip(labels, vals)):
        yy = y_dados - (i * 28)
        c.drawString(x, yy, label)
        c.setFont('Helvetica-Bold', 11)
        c.setFillColor(HexColor('#222222'))
        c.drawString(x, yy - 14, val)
        c.setFont('Helvetica-Bold', 9)
        c.setFillColor(HexColor('#888888'))
        if i < len(labels) - 1:
            c.setStrokeColor(HexColor('#eeeeee'))
            c.setLineWidth(0.5)
            c.line(x, yy - 24, w - 40, yy - 24)
    c.restoreState()

    # Número e validade da carteira em destaque
    c.saveState()
    barra_y = h - 365
    c.setFillColor(CDOA_BLUE)
    c.rect(35, barra_y, w - 70, 55, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont('Helvetica', 9)
    c.drawString(50, barra_y + 35, 'Nº DA CARTEIRA')
    c.setFont('Helvetica-Bold', 18)
    c.drawString(50, barra_y + 12, carteira.numero_carteira)
    c.setFont('Helvetica', 9)
    c.drawCentredString(w - 100, barra_y + 35, 'VALIDADE')
    c.setFont('Helvetica-Bold', 14)
    c.drawCentredString(w - 70, barra_y + 14, carteira.data_validade.strftime('%d/%m/%Y'))
    c.restoreState()

    # Código de barras simulado
    bc_y = h - 440
    c.saveState()
    c.setStrokeColor(HexColor('#333333'))
    c.setLineWidth(1)
    barcode = carteira.numero_carteira.replace('CDOA-', '').replace('-', '')
    for i, ch in enumerate(barcode):
        if ch.isdigit():
            c.setLineWidth(int(ch) / 2 + 0.5)
        else:
            c.setLineWidth(2)
        xx = 50 + i * 4
        if xx < w - 50:
            c.line(xx, bc_y, xx, bc_y + 30)
    c.setFont('Courier', 8)
    c.setFillColor(HexColor('#555555'))
    num_visivel = carteira.numero_carteira
    c.drawCentredString(w / 2, bc_y - 15, num_visivel)
    c.restoreState()

    # QR Code simulado
    c.saveState()
    qr_x, qr_y = w - 90, h - 470
    c.setStrokeColor(HexColor('#333333'))
    c.setLineWidth(0.5)
    c.rect(qr_x, qr_y, 30, 30)
    c.setFillColor(HexColor('#333333'))
    size = 30
    cells = 8
    for row in range(cells):
        for col in range(cells):
            if (row + col) % 3 != 0 and (row * col) % 5 != 0:
                cx = qr_x + (col / cells) * size
                cy = qr_y + ((cells - 1 - row) / cells) * size
                c.rect(cx, cy, size / cells, size / cells, fill=1, stroke=0)
    c.setFont('Helvetica', 5)
    c.setFillColor(HexColor('#999999'))
    c.drawCentredString(w - 75, qr_y - 10, 'QR Code')
    c.restoreState()

    # Texto legal
    c.saveState()
    legal_y = h - 510
    c.setFont('Helvetica-Oblique', 7.5)
    c.setFillColor(HexColor('#888888'))
    textos = [
        'A presente Carteira Profissional é o documento de identificação do Despachante Oficial',
        'devidamente habilitado a exercer a actividade de despachante aduaneiro em território nacional,',
        'ao abrigo do Estatuto da CDOA e demais legislação aplicável.',
    ]
    for i, t in enumerate(textos):
        c.drawCentredString(w / 2, legal_y - (i * 11), t)
    c.restoreState()

    # Hash
    raw = f'{carteira.numero_carteira}-{despachante.id}-{datetime.datetime.now().isoformat()}'
    doc_hash = hashlib.sha256(raw.encode()).hexdigest()[:20]
    c.saveState()
    c.setFont('Courier', 6)
    c.setFillColor(HexColor('#aaaaaa'))
    c.drawString(35, 65, f'SHA-256: {doc_hash}...')
    c.restoreState()

    # Selo dourado
    c.saveState()
    c.setStrokeColor(CDOA_GOLD)
    c.setLineWidth(3)
    cx, cy = w - 75, h - 120
    c.circle(cx, cy, 18)
    c.setFillColor(CDOA_GOLD)
    c.setFont('Helvetica-Bold', 9)
    c.drawCentredString(cx, cy - 4, 'CDOA')
    c.restoreState()

    c.saveState()
    c.setFont('Helvetica', 8)
    c.setFillColor(HexColor('#aaaaaa'))
    c.drawCentredString(w / 2, 16, f'Documento gerado electronicamente • {datetime.datetime.now().strftime("%d/%m/%Y %H:%M")} • Pág. 1/1')
    c.restoreState()

    _draw_footer(c)
    c.showPage()
    c.save()

    safe_number = carteira.numero_carteira.replace("/", "-").replace("\\", "-")
    pdf_filename = f'carteiras/{safe_number}.pdf'
    pdf_path = os.path.join(settings.MEDIA_ROOT, pdf_filename)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(buf.getvalue())

    return pdf_filename, f'/media/{pdf_filename}'
