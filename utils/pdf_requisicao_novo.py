import os
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from django.conf import settings

try:
    import qrcode
    QRCODE_OK = True
except:
    QRCODE_OK = False


def fmt_kz(valor):
    """Formata valor em KZ"""
    if not valor:
        return "0,00"
    try:
        if isinstance(valor, str):
            valor = Decimal(valor)
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)


def gerar_qr(dados):
    """Gera QR Code a partir de dados"""
    if not QRCODE_OK:
        return None
    try:
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2)
        qr.add_data(dados)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except:
        return None


def gerar_pdf_requisicao_profissional(requisicao, banca, cliente, processo, responsavel_dados):
    """Gera PDF da Requisição com layout profissional Netsulwel"""
    buffer = BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN = 1.0 * cm
    W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4, 
        leftMargin=MARGIN, 
        rightMargin=MARGIN, 
        topMargin=0.5*cm, 
        bottomMargin=1*cm
    )
    story = []
    
    # ─── Estilos ────────────────────────────────────────────────────────────
    def st(name, **kw):
        d = dict(fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#000000'), leading=10)
        d.update(kw)
        return ParagraphStyle(name, **d)
    
    # ─── CABEÇALHO: Logo (esquerda) + QR Code (direita) ──────────────────────
    col_logo = [Paragraph('<b>LOGO</b>', st('logo', fontSize=10))]
    if banca and banca.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, str(banca.logo))
            if os.path.exists(logo_path):
                col_logo = [RLImage(logo_path, width=1.8*cm, height=1.5*cm)]
        except:
            pass
    
    col_qr = [Paragraph('<b>QR</b>', st('qr', fontSize=9, alignment=TA_CENTER))]
    if QRCODE_OK:
        try:
            data_str = requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else '—'
            qr_data = f"RF:{requisicao.numero_requisicao}|{data_str}|{fmt_kz(requisicao.total_geral)}"
            qr_img = gerar_qr(qr_data)
            if qr_img:
                col_qr = [RLImage(qr_img, width=2.0*cm, height=2.0*cm)]
        except:
            pass
    
    # Dados da empresa (banca)
    empresa_txt = f'<b>{(banca.nome if banca else "DESPACHANTE").upper()}</b><br/><font size="7">{(banca.endereco or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</font><br/><font size="6">Tel: {(banca.telefone or "—").replace("&", "&amp;")}</font><br/><font size="6">Email: {(banca.email or "—").replace("&", "&amp;")}</font><br/><font size="6">NIF: {(banca.nif or "—").replace("&", "&amp;")}</font>'
    
    # Dados do cliente
    cliente_txt = f'<b>Emitido para:</b><br/><b>{(cliente.nome if cliente else "—").upper()}</b><br/><font size="7">{(cliente.localizacao or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</font><br/><font size="6">Email: {(cliente.email or "—").replace("&", "&amp;")}</font>'
    
    # Header com 3 colunas: Logo | Espaço | QR + Cliente
    header = Table([[
        Table([[col_logo], [Paragraph(empresa_txt, st('emp', fontSize=6, leading=8))]], colWidths=[2.0*cm]),
        Spacer(0.3*cm, 1),
        Table([[col_qr], [Paragraph(cliente_txt, st('cli', fontSize=6, leading=8))]], colWidths=[2.5*cm])
    ]], colWidths=[2.2*cm, 0.3*cm, 2.5*cm])
    
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 0.15*cm))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor('#000000')))
    story.append(Spacer(1, 0.1*cm))
    
    # ─── TÍTULO ────────────────────────────────────────────────────────────────
    story.append(Paragraph(f'Original', st('orig', fontSize=7)))
    story.append(Paragraph(f'<b>Fatura nº {requisicao.numero_requisicao}</b>', st('tit', fontSize=11, fontName='Helvetica-Bold')))
    story.append(Spacer(1, 0.1*cm))
    story.append(HRFlowable(width=W, thickness=1.5, color=colors.HexColor('#000000')))
    story.append(Spacer(1, 0.15*cm))
    
    # ─── INFORMAÇÕES: Data, Validade, Emissão, NIF ─────────────────────────────
    data_em = requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else '—'
    data_val = requisicao.data_validade.strftime('%d/%m/%Y') if requisicao.data_validade else '—'
    
    info = [[
        Paragraph('<b>Data Doc.</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)), 
        Paragraph(data_em, st('id', fontSize=6)),
        Paragraph('<b>Validade</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)), 
        Paragraph(data_val, st('id', fontSize=6)),
        Paragraph('<b>Emissão</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)), 
        Paragraph(f'{datetime.now().strftime("%d/%m/%Y %H:%M")}', st('id', fontSize=6)),
        Paragraph('<b>Contr.</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)), 
        Paragraph(f'{banca.nif if banca else "—"}', st('id', fontSize=6)),
    ]]
    
    t_info = Table(info, colWidths=[W*0.14, W*0.14, W*0.14, W*0.14, W*0.14, W*0.14, W*0.10, W*0.16])
    t_info.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor('#000000')))
    story.append(Spacer(1, 0.15*cm))
    
    # ─── TABELA DE LINHAS ───────────────────────────────────────────────────────
    valor_total = fmt_kz(requisicao.total_geral) if requisicao.total_geral else '0,00'
    
    linhas = [[
        Paragraph('<b>Código</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Descrição</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Preço Unit.</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Qtd.</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Taxa %</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Desc %</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
        Paragraph('<b>Total</b>', st('lh', fontName='Helvetica-Bold', fontSize=7)),
    ], [
        Paragraph('<font size="6">001</font>', st('ld')),
        Paragraph(f'<font size="6">{requisicao.mercadoria_descricao or "Serviço"}</font>', st('ld')),
        Paragraph(f'<font size="6">{valor_total}</font>', st('ld', alignment=TA_RIGHT)),
        Paragraph('<font size="6">1</font>', st('ld', alignment=TA_CENTER)),
        Paragraph('<font size="6">14.00</font>', st('ld', alignment=TA_CENTER)),
        Paragraph('<font size="6">0.00</font>', st('ld', alignment=TA_CENTER)),
        Paragraph(f'<font size="6"><b>{valor_total}</b></font>', st('ld', alignment=TA_RIGHT, fontName='Helvetica-Bold')),
    ]]
    
    t_lin = Table(linhas, colWidths=[W*0.08, W*0.30, W*0.12, W*0.08, W*0.10, W*0.10, W*0.22])
    t_lin.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_lin)
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width=W, thickness=1, color=colors.HexColor('#000000')))
    story.append(Spacer(1, 0.2*cm))
    
    # ─── IMPOSTOS/IVA ──────────────────────────────────────────────────────────
    impostos = [[
        Paragraph('<b>Imposto/IVA %</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)),
        Paragraph('<b>Incidência</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)),
        Paragraph('<b>Valor</b>', st('ih', fontName='Helvetica-Bold', fontSize=6)),
    ], [
        Paragraph('<font size="6">IVA - 14.00</font>', st('id')),
        Paragraph(f'<font size="6">{valor_total}</font>', st('id', alignment=TA_CENTER)),
        Paragraph(f'<font size="6">{fmt_kz(requisicao.iva_honorarios) if requisicao.iva_honorarios else "0,00"}</font>', st('id', alignment=TA_RIGHT)),
    ]]
    t_imp = Table(impostos, colWidths=[W*0.15, W*0.20, W*0.15])
    t_imp.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    # ─── RESUMO FINANCEIRO (2 COLUNAS) ─────────────────────────────────────────
    resumo = [[
        Paragraph('<b>Sumário</b>', st('rh', fontName='Helvetica-Bold', fontSize=6)), 
        Paragraph('', st('rh')),
    ], [
        Paragraph('<font size="6">Total ilíquido:</font>', st('rs')), 
        Paragraph(f'<font size="6">{valor_total}</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="6">Desconto:</font>', st('rs')), 
        Paragraph('<font size="6">0,00</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="6">Despesas:</font>', st('rs')), 
        Paragraph('<font size="6">0,00</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="6">Total c/ Descontos:</font>', st('rs')), 
        Paragraph(f'<font size="6">{valor_total}</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="6">Total Impostos:</font>', st('rs')), 
        Paragraph(f'<font size="6">{fmt_kz(requisicao.iva_honorarios) if requisicao.iva_honorarios else "0,00"}</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="6">Retenção: (0%)</font>', st('rs')), 
        Paragraph(f'<font size="6">{fmt_kz(requisicao.retencao) if requisicao.retencao else "0,00"}</font>', st('rs', alignment=TA_RIGHT)),
    ], [
        Paragraph('<font size="7"><b>Total:</b></font>', st('tot', fontName='Helvetica-Bold', fontSize=7)), 
        Paragraph(f'<font size="7"><b>{valor_total}</b></font>', st('tot', alignment=TA_RIGHT, fontName='Helvetica-Bold', fontSize=7)),
    ]]
    t_res = Table(resumo, colWidths=[W*0.50, W*0.30])
    t_res.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LINEABOVE', (0, 7), (-1, 7), 1.5, colors.HexColor('#000000')),
    ]))
    
    # Combinar Impostos (esquerda) + Resumo (direita)
    resumo_comp = Table([[t_imp, Spacer(0.2*cm, 1), t_res]], colWidths=[W*0.35, 0.2*cm, W*0.65-0.2*cm])
    resumo_comp.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(resumo_comp)
    story.append(Spacer(1, 0.3*cm))
    
    # ─── VALOR TOTAL DO PROCESSO ADUANEIRO ──────────────────────────────────────
    valor_proc = fmt_kz(processo.total_geral) if processo and hasattr(processo, 'total_geral') and processo.total_geral else '0,00'
    story.append(Paragraph(
        f'<b>Valor Total do Processo Aduaneiro: {valor_proc} KZ</b>', 
        st('proc', fontName='Helvetica-Bold', fontSize=8)
    ))
    story.append(Spacer(1, 0.2*cm))
    
    # ─── BENS E SERVIÇOS + DADOS BANCÁRIOS ──────────────────────────────────────
    bens = [[
        Paragraph('<b>Bens e Serviços</b>', st('bh', fontName='Helvetica-Bold', fontSize=6)),
        Paragraph('<b>Dados Bancários</b>', st('bh', fontName='Helvetica-Bold', fontSize=6)),
    ], [
        Paragraph('<font size="6">Os bens/serviços foram colocados à disposição na data e local do documento</font>', st('bd')),
        Paragraph(
            f'<font size="6"><b>IBAN:</b> {getattr(banca, "iban", "—") if banca else "—"}<br/><b>SWIFT:</b> {getattr(banca, "swift", "—") if banca else "—"}</font>', 
            st('bd')
        ),
    ]]
    t_ben = Table(bens, colWidths=[W*0.50, W*0.50])
    t_ben.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8e8e8')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#000000')),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('VALIGN', (0, 1), (-1, 1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ben)
    
    # Construir PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
