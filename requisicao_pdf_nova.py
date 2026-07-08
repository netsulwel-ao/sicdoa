@requer_sessao_ativa
def requisicao_pdf(request, pk):
    """Gera PDF da Requisição de Fundos com layout profissional"""
    from datetime import datetime
    from decimal import Decimal
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from users.models import Usuario
    
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    buffer = io.BytesIO()
    
    PAGE_W, PAGE_H = A4
    MARGIN = 0.7 * cm
    W = PAGE_W - 2 * MARGIN
    
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title=f"Requisição de Fundos {requisicao.numero_requisicao}",
    )
    
    # Cores
    COR_PRETO = colors.HexColor('#0f172a')
    COR_CINZA = colors.HexColor('#64748b')
    COR_BORDA = colors.HexColor('#cbd5e1')
    COR_VERMELHO = colors.HexColor('#dc2626')
    
    # Estilos
    def st(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRETO, leading=11)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)
    
    s_small = st('small', fontSize=6.5, textColor=COR_CINZA, leading=8)
    
    banca = requisicao.banca
    cliente = requisicao.cliente
    processo = requisicao.processo_aduaneiro
    
    # Nome do despachante responsável
    responsavel_nome = 'DESPACHANTE OFICIAL'
    if banca:
        try:
            usuario_banca = Usuario.objects.get(id=banca.usuario_id)
            responsavel_nome = (usuario_banca.nome or 'DESPACHANTE OFICIAL').upper()
        except:
            responsavel_nome = 'DESPACHANTE OFICIAL'
    
    story = []
    
    # Cabeçalho com data e hora
    agora = datetime.now()
    top_line = Table([[
        Paragraph('', st('empty')),
        Paragraph(f'<font size="6.5" color="#999">Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>', st('top', alignment=TA_RIGHT, fontSize=6.5))
    ]], colWidths=[W * 0.6, W * 0.4])
    top_line.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(top_line)
    story.append(Spacer(1, 0.15 * cm))
    
    # Logo e NIF
    nif_txt = f"NIF: {banca.nif}" if banca else 'N/D'
    nome_txt = banca.nome if banca else 'Despachante Oficial'
    
    header_table = Table([[
        Paragraph(f'<font size="10"><b>{nome_txt}</b></font>', st('nome', fontName='Helvetica-Bold', fontSize=10.5)),
        Paragraph(f'<font size="8" color="#666"><b>{nif_txt}</b></font>', st('nif', fontSize=8, alignment=TA_RIGHT))
    ]], colWidths=[W * 0.7, W * 0.3])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(header_table)
    
    # Despachante em verde
    story.append(Paragraph(
        f'<font size="9" color="#059669"><b>{responsavel_nome}</b></font>',
        st('resp', fontName='Helvetica-Bold', fontSize=9)
    ))
    story.append(Spacer(1, 0.05 * cm))
    
    # Banca - HASH
    story.append(Paragraph(
        f'<font size="7"><b>{nome_txt} - HASH</b></font>',
        st('hash', fontName='Helvetica-Bold', fontSize=7)
    ))
    story.append(Paragraph(
        '<font size="6.5">Processado por programa válido nº35/AGT/2019</font>',
        s_small
    ))
    
    # Endereço e contatos
    endereco = banca.endereco if banca else ''
    telefone = banca.telefone if banca else ''
    email_b = banca.email if banca else ''
    cdoa = banca.licenca_cdoa if banca else ''
    
    for info in filter(None, [endereco, 'ANGOLA', f'Tel: {telefone}' if telefone else '', f'Email: {email_b}' if email_b else '', f'Cédula CDOA: {cdoa}' if cdoa else '']):
        story.append(Paragraph(f'<font size="6.5" color="#666">{info}</font>', s_small))
    
    story.append(Spacer(1, 0.15 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.15 * cm))
    
    # Requisição Nº e Data
    data_emissao = requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else 'N/D'
    
    req_table = Table([[
        Paragraph(f'<font size="9.5"><b>Requisição Nº: {requisicao.numero_requisicao}</b></font>', st('req', fontName='Helvetica-Bold', fontSize=9.5)),
        Paragraph(f'<font size="9.5"><b>Data: {data_emissao}</b></font>', st('data', fontName='Helvetica-Bold', fontSize=9.5, alignment=TA_RIGHT))
    ]], colWidths=[W * 0.55, W * 0.45])
    req_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(req_table)
    story.append(Spacer(1, 0.2 * cm))
    
    # Tabela 3 colunas
    valor_aduaneiro = processo.valor_total if processo and hasattr(processo, 'valor_total') else requisicao.valor_cif or Decimal('0')
    
    designacao_text = f"""<b>Designação da mercadoria</b>

Pelo desembarque de:
<b>{requisicao.mercadoria_descricao or (processo.descricao_mercadoria if processo else 'N/D')}</b>

<b>Documentos</b>
BL ou Carta: {requisicao.numero_bl_awb or '—'}
Procedência: {requisicao.origem or '—'}
Navio/Avião: {requisicao.meio_transporte or '—'}
Nr DU: {processo.numero_du if processo else '—'}
Valor CIF: {fmt_kz(requisicao.valor_cif) if requisicao.valor_cif else '—'}
Câmbio: {requisicao.cambio_referencia or '—'}
Valor aduaneiro: {fmt_kz(valor_aduaneiro)}"""
    
    despesas_doc = requisicao.linhas.filter(documentada=True)
    total_direitos = Decimal('0')
    direitos_text = '<b>Direitos e mais imposições</b>\n\n'
    
    for linha in despesas_doc:
        if linha.valor and linha.valor > 0:
            direitos_text += f"{linha.despesa_tipo or 'Despesa'} ..... {fmt_kz(linha.valor)}\n"
            total_direitos += linha.valor
    
    if total_direitos == 0:
        direitos_text += "EP 14 .................\nEP 15 .................\nEP 17 ..................."
    
    despesas_nao_doc = requisicao.linhas.filter(documentada=False)
    total_despesas = Decimal('0')
    despesas_text = '<b>Despesas inerentes</b>\n\n'
    
    for linha in despesas_nao_doc:
        if linha.valor and linha.valor > 0:
            despesas_text += f"{linha.despesa_tipo or 'Despesa'} ..... {fmt_kz(linha.valor)}\n"
            total_despesas += linha.valor
    
    if total_despesas == 0:
        despesas_text += "Honorários: —"
    
    tres_colunas = Table([[
        Paragraph(designacao_text, st('designacao', fontSize=6.5, leading=8)),
        Paragraph(direitos_text, st('direitos', fontSize=6.5, leading=8)),
        Paragraph(despesas_text, st('despesas', fontSize=6.5, leading=8))
    ]], colWidths=[W/3 - 0.15*cm, W/3 - 0.15*cm, W/3 - 0.15*cm])
    
    tres_colunas.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, COR_BORDA),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tres_colunas)
    story.append(Spacer(1, 0.2 * cm))
    
    # Totalizações
    cambio = Decimal(requisicao.cambio_referencia or 1)
    if cambio == 0:
        cambio = Decimal(1)
    valor_usd = requisicao.total_geral / cambio if requisicao.total_geral else Decimal('0')
    
    totais = Table([
        [Paragraph('<font size="7"><b>Mercadorias</b></font>', st('tot')), Paragraph(f'<font size="7" color="{COR_VERMELHO}"><b>{fmt_kz(total_direitos)}</b></font>', st('tot')), 
         Paragraph('<font size="7"><b>Serviços</b></font>', st('tot')), Paragraph(f'<font size="7" color="{COR_VERMELHO}"><b>{fmt_kz(total_despesas)}</b></font>', st('tot'))],
        [Paragraph('<font size="7">Outros</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot')), 
         Paragraph('<font size="7">IEC</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot'))],
        [Paragraph('<font size="7">Retenção</font>', st('tot')), Paragraph(f'<font size="7">{fmt_kz(requisicao.retencao) if requisicao.retencao else "0,00"}</font>', st('tot')), 
         Paragraph('<font size="7">Descontos</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot'))],
        [Paragraph('<font size="7"><b>TOTAL Kz:</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph(f'<font size="8" color="{COR_VERMELHO}"><b>{fmt_kz(requisicao.total_geral or 0)}</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph('<font size="7"><b>TOTAL USD:</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph(f'<font size="8" color="{COR_VERMELHO}"><b>{fmt_kz(valor_usd)}</b></font>', st('tot', fontName='Helvetica-Bold'))],
    ], colWidths=[2.2*cm, 2.5*cm, 2.2*cm, 2.5*cm])
    
    totais.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(totais)
    story.append(Spacer(1, 0.2 * cm))
    
    # Nota
    story.append(Paragraph(
        '<font size="6.5"><i>NOTA: Os originais das contas referidas vão devediamente selecionadas pelo valor dos honorários</i></font>',
        st('nota', fontSize=6.5, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    # Assinatura
    assinatura = Table([
        [Paragraph('Recebeu em: _____/_____/______', st('ass', fontSize=7)), 
         Paragraph('O Cliente', st('ass', fontSize=7, alignment=TA_CENTER))],
        [Paragraph('', st('ass', fontSize=1)), 
         Paragraph(f'<b>{responsavel_nome}</b>', st('ass', fontSize=7.5, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ], colWidths=[W/2, W/2])
    
    assinatura.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(assinatura)
    story.append(Spacer(1, 0.15 * cm))
    
    # Dados do cliente
    cliente_nome = cliente.nome if cliente else 'Nome do Cliente'
    cliente_loc = cliente.localizacao if cliente else 'Endereço'
    cliente_tel = cliente.telefone if cliente else 'Telefone'
    
    story.append(Paragraph(f'<font size="8"><b>{cliente_nome}</b></font>', st('cli', fontName='Helvetica-Bold', fontSize=8)))
    story.append(Paragraph(f'<font size="6.5">{cliente_loc} - Tel {cliente_tel}</font>', s_small))
    
    # Construir PDF
    doc.build(story)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Requisicao_{requisicao.numero_requisicao}.pdf"'
    return response
