"""Views do módulo aduaneiro — DU (Declaração Única)."""
import io
import json
import uuid

from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from clientes.models import Cliente
from users.models import Usuario
from utils.validators import email_ja_existe
from django.core.paginator import Paginator
from .models import DeclaracaoUnica


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sessao_ok(request):
    return bool(request.session.get('usuario_id'))


def _usuario_id(request):
    return request.session.get('usuario_id')


def _papel(request):
    return request.session.get('usuario', {}).get('papel', '')


def _ctx_base(request):
    u = request.session.get('usuario', {})
    return {'usuario': u, 'nome': u.get('nome', ''), 'papel': u.get('papel', '')}


# ─── DU — Criar / Editar ─────────────────────────────────────────────────────

def du_view(request, du_uuid=None):
    """Formulário de criação ou edição de DU."""
    if not _sessao_ok(request):
        return redirect('login')

    du = None
    dados_iniciais = '{}'
    dono_du = None          # dados do proprietário da DU (para o admin ver)
    is_admin_editando = False

    if du_uuid:
        du = get_object_or_404(DeclaracaoUnica, du_uuid=du_uuid)
        papel_atual = _papel(request)
        uid_atual   = _usuario_id(request)

        # Só o dono ou Administrador pode editar
        if du.usuario_id != uid_atual and papel_atual != 'Administrador':
            return redirect('du_lista')

        dados_iniciais = du.dados_json

        # Se é admin a editar uma DU de outro utilizador, buscar dados do dono
        if papel_atual == 'Administrador' and du.usuario_id != uid_atual:
            is_admin_editando = True
            try:
                dono = Usuario.objects.get(id=du.usuario_id)
                dono_du = {
                    'nome':    dono.nome,
                    'nif':     dono.nif or '',
                    'cedula':  dono.cedula or '',
                    'papel':   dono.papel,
                    'email':   dono.email,
                    'telefone': dono.telefone or '',
                }
            except Usuario.DoesNotExist:
                # Fallback: usar dados guardados no dados_json
                dados_guardados = du.get_dados()
                dono_du = {
                    'nome':   dados_guardados.get('despachante_nome', du.nome_declarante or ''),
                    'nif':    dados_guardados.get('despachante_nif',  du.nif_declarante  or ''),
                    'cedula': dados_guardados.get('despachante_licenca', ''),
                    'papel':  'Despachante Oficial',
                    'email':  '',
                    'telefone': '',
                }

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'du': du,
        'dados_iniciais': dados_iniciais,
        'is_admin_editando': is_admin_editando,
        'dono_du': dono_du,
    })
    return render(request, 'du.html', ctx)


# ─── DU — Guardar (rascunho ou submissão) ────────────────────────────────────

@require_POST
def du_guardar(request):
    """Guarda ou actualiza uma DU via AJAX (JSON body)."""
    # Debug: verificar sessão
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"=== DEBUG du_guardar ===")
    logger.info(f"Session keys: {list(request.session.keys())}")
    logger.info(f"usuario_id: {request.session.get('usuario_id')}")
    logger.info(f"Session cookie: {request.COOKIES.get('sessionid', 'NONE')}")
    logger.info(f"Headers: {dict(request.headers)}")
    
    if not _sessao_ok(request):
        logger.warning("Sessão não OK - retornando 401")
        return JsonResponse({'erro': 'Não autorizado'}, status=401)

    try:
        payload = json.loads(request.body)
        logger.info(f"Payload recebido: {json.dumps(payload, indent=2, ensure_ascii=False)[:1000]}...")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    du_uuid   = payload.get('uuid')
    submeter  = payload.get('submeter', False)
    dados     = payload.get('dados', {})
    totais    = payload.get('totais', {})

    uid = _usuario_id(request)

    # ── Normalizar e validar totais recebidos ─────────────────────────────
    def _safe_float(v, default=0.0):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return default

    t_derimp = _safe_float(totais.get('derimp', 0))
    t_iec    = _safe_float(totais.get('iec',    0))
    t_emgead = _safe_float(totais.get('emgead', 0))
    t_direxp = _safe_float(totais.get('direxp', 0))
    t_iva    = _safe_float(totais.get('iva',    0))
    # Recalcular total server-side para garantir consistência
    t_total  = t_derimp + t_iec + t_emgead + t_direxp + t_iva

    # ── Normalizar impostos por adição ────────────────────────────────────
    adicoes = dados.get('adicoes', [])
    for ad in adicoes:
        # Se o frontend enviou impostos como objecto, garantir que está bem formado
        imp = ad.get('impostos')
        if isinstance(imp, dict):
            for cod, info in imp.items():
                if isinstance(info, dict):
                    info['valor'] = _safe_float(info.get('valor', 0))
                    info['taxa']  = _safe_float(info.get('taxa',  0))
                    info['base']  = _safe_float(info.get('base',  0))
        # Garantir que montante_kz e fob_kz são numéricos
        for campo in ('montante_kz', 'fob_kz', 'seguro_kz', 'frete_kz',
                      'valor_fob', 'valor_seguro', 'valor_frete',
                      'valor_fob_kz', 'valor_seguro_kz', 'valor_frete_kz',
                      'reparticao_seguro', 'reparticao_frete'):
            if campo in ad and ad[campo] == '':
                ad[campo] = '0'
    dados['adicoes'] = adicoes

    # ── Validação server-side dos campos obrigatórios ─────────────────────
    erros = []

    # Validações básicas apenas para submissão final
    if submeter:
        regime = (dados.get('regime_aduaneiro', '') or '').strip()
        if not regime:
            erros.append('Regime Aduaneiro é obrigatório.')

        ref = (dados.get('ref_despachante', '') or '').strip()
        if not ref:
            erros.append('Referência Interna é obrigatória.')

        if not (dados.get('exportador_nome', '') or '').strip() and \
           not (dados.get('exportador_codigo', '') or '').strip():
            erros.append('Dados do Exportador (nome ou NIF) são obrigatórios.')

        adicoes = dados.get('adicoes', [])
        if not adicoes:
            erros.append('A DU deve ter pelo menos uma adição.')
        else:
            for i, ad in enumerate(adicoes, 1):
                if not (ad.get('codigo_pautal', '') or '').strip():
                    erros.append(f'Adição {i}: Código Pautal é obrigatório.')
                if not (ad.get('pais_origem', '') or '').strip():
                    erros.append(f'Adição {i}: País de Origem é obrigatório.')

        forma_pag = (dados.get('forma_pagamento', '') or '').strip()
        if not forma_pag:
            erros.append('Forma de Pagamento é obrigatória.')
    else:
        # Para rascunhos, apenas validações mínimas
        regime = (dados.get('regime_aduaneiro', '') or '').strip()
        if not regime:
            erros.append('Regime Aduaneiro é obrigatório.')

        ref = (dados.get('ref_despachante', '') or '').strip()
        if not ref:
            erros.append('Referência Interna é obrigatória.')

    # ── Validação de totais: Step 1 vs Adições (só na submissão final) ───────
    if submeter:
        fob_step1 = _safe_float(dados.get('valor_fob_kz', 0))
        frete_step1 = _safe_float(dados.get('valor_frete_kz', 0))
        seguro_step1 = _safe_float(dados.get('valor_seguro_kz', 0))

        fob_total = sum(_safe_float(ad.get('fob_kz', 0)) for ad in dados.get('adicoes', []))
        frete_total = sum(_safe_float(ad.get('frete_kz', 0)) for ad in dados.get('adicoes', []))
        seguro_total = sum(_safe_float(ad.get('seguro_kz', 0)) for ad in dados.get('adicoes', []))

        # Margem de 1 KZ para arredondamentos de câmbio
        margem = 1.0

        logger.info(f"Validação de totais (submissão):")
        logger.info(f"  FOB Step1: {fob_step1:.2f} | Adições: {fob_total:.2f} | Diff: {abs(fob_step1 - fob_total):.2f}")
        logger.info(f"  Frete Step1: {frete_step1:.2f} | Adições: {frete_total:.2f} | Diff: {abs(frete_step1 - frete_total):.2f}")
        logger.info(f"  Seguro Step1: {seguro_step1:.2f} | Adições: {seguro_total:.2f} | Diff: {abs(seguro_step1 - seguro_total):.2f}")

        if fob_step1 > 0 and fob_total > 0 and abs(fob_step1 - fob_total) > margem:
            erros.append(f'FOB do Step 1 ({fob_step1:.2f} KZ) não corresponde ao total das adições ({fob_total:.2f} KZ). Diferença: {abs(fob_step1 - fob_total):.2f} KZ')

        if frete_step1 > 0 and frete_total > 0 and abs(frete_step1 - frete_total) > margem:
            erros.append(f'Frete do Step 1 ({frete_step1:.2f} KZ) não corresponde ao total das adições ({frete_total:.2f} KZ). Diferença: {abs(frete_step1 - frete_total):.2f} KZ')

        if seguro_step1 > 0 and seguro_total > 0 and abs(seguro_step1 - seguro_total) > margem:
            erros.append(f'Seguro do Step 1 ({seguro_step1:.2f} KZ) não corresponde ao total das adições ({seguro_total:.2f} KZ). Diferença: {abs(seguro_step1 - seguro_total):.2f} KZ')
    else:
        logger.info("Rascunho: validação de totais ignorada")

    if erros:
        logger.warning(f"Erros de validação: {erros}")
        return JsonResponse({'erro': ' | '.join(erros), 'erros': erros}, status=400)

    if du_uuid:
        try:
            du = DeclaracaoUnica.objects.get(du_uuid=du_uuid)
            if du.usuario_id != uid and _papel(request) != 'Administrador':
                return JsonResponse({'erro': 'Sem permissão'}, status=403)
        except DeclaracaoUnica.DoesNotExist:
            du = DeclaracaoUnica(usuario_id=uid, processo_id=None)
    else:
        du = DeclaracaoUnica(usuario_id=uid, processo_id=None)

    # Preencher campos desnormalizados
    du.regime_aduaneiro   = (dados.get('regime_aduaneiro', '') or '')[:100]
    du.ref_despachante    = (dados.get('ref_despachante',  '') or '')[:100]
    du.exportador_nome    = (dados.get('exportador_nome',  '') or '')[:200]
    du.destinatario_nome  = (dados.get('destinatario_nome','') or '')[:200]
    du.nome_declarante    = (dados.get('exportador_nome',  '') or '')[:200]
    du.nif_declarante     = (dados.get('exportador_codigo','') or '')[:50]
    du.codigo_pautal      = ''   # campo obrigatório na tabela — deixar vazio
    du.descricao_mercadoria = ''
    du.quantidade         = 0
    du.peso_bruto         = 0
    du.peso_liquido       = 0

    # Totais por imposto
    du.total_derimp  = t_derimp
    du.total_iec     = t_iec
    du.total_emgead  = t_emgead
    du.total_direxp  = t_direxp
    du.total_iva     = t_iva
    du.total_geral   = t_total

    # Totais nos campos originais da tabela
    du.direitos_aduaneiros = du.total_derimp
    du.imposto_consumo     = du.total_iec
    du.emolumentos         = du.total_emgead
    du.iva                 = du.total_iva
    du.total_impostos      = du.total_geral

    # Valores financeiros
    try:
        du.valor_fob    = float(dados.get('valor_fob_kz',    0) or 0)
        du.valor_frete  = float(dados.get('valor_frete_kz',  0) or 0)
        du.valor_seguro = float(dados.get('valor_seguro_kz', 0) or 0)
    except (TypeError, ValueError):
        du.valor_fob = du.valor_frete = du.valor_seguro = 0
    du.valor_cif = du.valor_fob + du.valor_frete + du.valor_seguro

    du.set_dados(dados)

    # Gerar UUID e código de processo se novo registo
    if not du.du_uuid:
        du.du_uuid = str(uuid.uuid4())
    if not du.codigo_processo:
        du.codigo_processo = DeclaracaoUnica.gerar_codigo_processo()

    if submeter:
        du.status = 'Aprovada'
        if not du.numero_du:
            du.numero_du = du.gerar_numero()
        du.data_submissao = timezone.now()
        du.data_aprovacao = timezone.now()
    else:
        du.status = 'Rascunho'
        # Rascunho não tem número — fica NULL até submeter
        if not du.numero_du:
            du.numero_du = None

    du.save()

    return JsonResponse({
        'sucesso': True,
        'uuid': du.du_uuid,
        'codigo_processo': du.codigo_processo or '',
        'numero_du': du.numero_du or '',
        'status': du.status,
    })


# ─── DU — Listar ─────────────────────────────────────────────────────────────

def du_lista(request):
    """Lista de DUs — filtrada por papel."""
    if not _sessao_ok(request):
        return redirect('login')

    papel = _papel(request)
    uid   = _usuario_id(request)

    if papel == 'Administrador':
        dus = DeclaracaoUnica.objects.all()
    else:
        # Despachante e Operador vêem as suas próprias DUs
        dus = DeclaracaoUnica.objects.filter(usuario_id=uid)

    # Filtros opcionais
    q      = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()

    if q:
        dus = dus.filter(
            Q(numero_du__icontains=q) |
            Q(codigo_processo__icontains=q) |
            Q(ref_despachante__icontains=q) |
            Q(exportador_nome__icontains=q) |
            Q(destinatario_nome__icontains=q) |
            Q(nome_declarante__icontains=q)
        )
    if status:
        dus = dus.filter(status=status)

    paginator = Paginator(dus, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'page_obj': page_obj,
        'q': q,
        'status_filtro': status,
        'is_admin': papel == 'Administrador',
    })
    return render(request, 'du_lista.html', ctx)


# ─── DU — Detalhe ────────────────────────────────────────────────────────────

def du_detalhe(request, du_uuid):
    """Detalhe de uma DU."""
    if not _sessao_ok(request):
        return redirect('login')

    du = get_object_or_404(DeclaracaoUnica, du_uuid=du_uuid)
    papel = _papel(request)
    uid   = _usuario_id(request)

    if du.usuario_id != uid and papel not in ('Administrador', 'Operador'):
        return redirect('du_lista')

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'du',
        'du': du,
        'dados': du.get_dados(),
        'is_admin': papel == 'Administrador',
        'pode_editar': papel == 'Administrador' or du.usuario_id == uid,
    })
    return render(request, 'du_detalhe.html', ctx)


# ─── DU — Apagar (só Administrador) ─────────────────────────────────────────

@require_POST
def du_apagar(request, du_uuid):
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)
    if _papel(request) != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    du = get_object_or_404(DeclaracaoUnica, du_uuid=du_uuid)
    du.delete()
    return JsonResponse({'sucesso': True})


# ─── DU — Alterar status (só Administrador) ──────────────────────────────────

@require_POST
def du_alterar_status(request, du_uuid):
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)
    if _papel(request) != 'Administrador':
        return JsonResponse({'erro': 'Sem permissão'}, status=403)

    try:
        payload = json.loads(request.body)
        novo_status = payload.get('status', '')
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    status_validos = [s[0] for s in DeclaracaoUnica.STATUS_CHOICES]
    if novo_status not in status_validos:
        return JsonResponse({'erro': 'Status inválido'}, status=400)

    du = get_object_or_404(DeclaracaoUnica, du_uuid=du_uuid)
    du.status = novo_status
    du.save(update_fields=['status', 'updated_at'])
    return JsonResponse({'sucesso': True, 'status': du.status})


# ─── DU — Download PDF ───────────────────────────────────────────────────────

def du_download_pdf(request, du_uuid):
    """Gera e devolve o PDF da DU com todos os dados, despachante e campo de assinatura."""
    if not _sessao_ok(request):
        return redirect('login')

    du    = get_object_or_404(DeclaracaoUnica, du_uuid=du_uuid)
    papel = _papel(request)
    uid   = _usuario_id(request)

    if du.usuario_id != uid and papel not in ('Administrador', 'Operador'):
        return redirect('du_lista')

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        )

        # Buscar dados do despachante (proprietario da DU)
        try:
            dono = Usuario.objects.get(id=du.usuario_id)
            desp_nome     = dono.nome
            desp_nif      = dono.nif or ''
            desp_cedula   = dono.cedula or ''
            desp_papel    = dono.papel
            desp_email    = dono.email or ''
            desp_telefone = dono.telefone or ''
        except Usuario.DoesNotExist:
            dados_j = du.get_dados()
            desp_nome     = dados_j.get('despachante_nome',    du.nome_declarante or 'N/D')
            desp_nif      = dados_j.get('despachante_nif',     du.nif_declarante  or 'N/D')
            desp_cedula   = dados_j.get('despachante_licenca', 'N/D')
            desp_papel    = 'Despachante Oficial'
            desp_email    = ''
            desp_telefone = ''

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=1.8*cm, rightMargin=1.8*cm,
            topMargin=1.8*cm, bottomMargin=2*cm,
            title=f'DU {du.numero_du or du.du_uuid}',
        )
        W = A4[0] - 3.6*cm

        cor_primaria  = colors.HexColor('#137fec')
        cor_cabecalho = colors.HexColor('#0f172a')
        cor_linha_par = colors.HexColor('#f8fafc')
        cor_borda     = colors.HexColor('#e2e8f0')
        cor_label_bg  = colors.HexColor('#f1f5f9')

        s_secao = ParagraphStyle('secao',
            fontSize=10, fontName='Helvetica-Bold',
            textColor=cor_primaria, spaceBefore=10, spaceAfter=4)
        s_normal = ParagraphStyle('normal',
            fontSize=8.5, fontName='Helvetica',
            textColor=cor_cabecalho, leading=12)
        s_bold = ParagraphStyle('bold',
            fontSize=8.5, fontName='Helvetica-Bold',
            textColor=cor_cabecalho, leading=12)
        s_small = ParagraphStyle('small',
            fontSize=7.5, fontName='Helvetica',
            textColor=colors.HexColor('#64748b'), leading=10)
        s_assinatura = ParagraphStyle('assinatura',
            fontSize=8, fontName='Helvetica',
            textColor=colors.HexColor('#475569'), leading=11)

        story = []
        dados = du.get_dados()

        # Cabecalho
        status_cores = {
            'Aprovada':   ('#dcfce7', '#166534'),
            'Rascunho':   ('#fef9c3', '#854d0e'),
            'Rejeitada':  ('#fee2e2', '#991b1b'),
            'Submetida':  ('#dbeafe', '#1e40af'),
            'Em Analise': ('#f3e8ff', '#6b21a8'),
        }
        sc = status_cores.get(du.status, ('#f1f5f9', '#374151'))

        s_titulo = ParagraphStyle('titulo',
            fontSize=18, fontName='Helvetica-Bold',
            textColor=cor_cabecalho, spaceAfter=2)
        s_subtitulo = ParagraphStyle('subtitulo',
            fontSize=9, fontName='Helvetica',
            textColor=colors.HexColor('#64748b'), spaceAfter=0)

        header_data = [[
            Paragraph('DECLARACAO UNICA (DU)', s_titulo),
            Paragraph(
                f'<font color="{sc[1]}"><b>{du.status}</b></font>',
                ParagraphStyle('st', fontSize=10, fontName='Helvetica-Bold',
                               alignment=2)
            ),
        ]]
        t_header = Table(header_data, colWidths=[W - 3.5*cm, 3.5*cm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(t_header)
        story.append(Paragraph(
            f'N: <b>{du.numero_du or "Rascunho"}</b>  |  '
            f'Processo: <b>{du.codigo_processo or "N/D"}</b>  |  '
            f'Ref.: <b>{du.ref_despachante or "N/D"}</b>  |  '
            f'Data: <b>{du.created_at.strftime("%d/%m/%Y %H:%M")}</b>',
            s_subtitulo
        ))
        story.append(HRFlowable(width=W, thickness=2, color=cor_primaria, spaceAfter=8))

        def tabela_kv(linhas, col_label=5.5*cm):
            rows = []
            for k, v in linhas:
                rows.append([
                    Paragraph(str(k), s_small),
                    Paragraph(str(v) if v else 'N/D', s_normal),
                ])
            if not rows:
                return None
            t = Table(rows, colWidths=[col_label, W - col_label])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), cor_label_bg),
                ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, cor_linha_par]),
            ]))
            return t

        def titulo_secao(texto):
            story.append(Paragraph(texto, s_secao))

        # 1. IDENTIFICACAO
        titulo_secao('1. IDENTIFICACAO DA DECLARACAO')
        t = tabela_kv([
            ('Regime Aduaneiro',       dados.get('regime_aduaneiro', du.regime_aduaneiro)),
            ('Referencia Interna',     dados.get('ref_despachante',  du.ref_despachante)),
            ('Estancia',               dados.get('estancia', '')),
            ('Vinheta',                dados.get('vinheta_selecionada', dados.get('vinheta', ''))),
            ('INCOTERM',               dados.get('incoterm', '')),
            ('Natureza da Transacao',  dados.get('natureza_transacao', '')),
            ('Conta de Credito',       dados.get('conta_credito', '')),
            ('Conta de Garantia',      dados.get('conta_garantias', '')),
            ('Localizacao Mercadoria', dados.get('localizacao_mercadoria', '')),
            ('Identificacao Armazem',  dados.get('identificacao_armzem', '')),
        ])
        if t: story.append(t)

        # 2. EXPORTADOR
        titulo_secao('2. EXPORTADOR / REMETENTE')
        t = tabela_kv([
            ('Nome / Razao Social', dados.get('exportador_nome', du.exportador_nome)),
            ('NIF',                 dados.get('exportador_codigo', du.nif_declarante)),
            ('Endereco',            dados.get('exportador_endereco', '')),
        ])
        if t: story.append(t)

        # 3. DESTINATARIO
        titulo_secao('3. DESTINATARIO / CONSIGNATARIO')
        t = tabela_kv([
            ('Nome / Razao Social', dados.get('destinatario_nome', du.destinatario_nome)),
            ('NIF',                 dados.get('destinatario_nif', '')),
            ('Telefone',            dados.get('destinatario_telefone', '')),
            ('Endereco',            dados.get('destinatario_endereco', '')),
        ])
        if t: story.append(t)

        # 4. DESPACHANTE
        titulo_secao('4. DESPACHANTE / DECLARANTE')
        t = tabela_kv([
            ('Nome Completo',       desp_nome),
            ('Papel / Funcao',      desp_papel),
            ('NIF',                 desp_nif),
            ('N Cedula / Licenca',  desp_cedula),
            ('Email',               desp_email),
            ('Telefone',            desp_telefone),
        ])
        if t: story.append(t)

        # 5. INFORMACOES COMERCIAIS
        titulo_secao('5. INFORMACOES COMERCIAIS E FINANCEIRAS')
        t = tabela_kv([
            ('Valor FOB',           f"{dados.get('valor_fob', '0')} {dados.get('moeda_fob', '')}"),
            ('Cambio FOB',          dados.get('cambio_fob', '')),
            ('Valor FOB (KZ)',       dados.get('valor_fob_kz', '')),
            ('Valor Seguro',        f"{dados.get('valor_seguro', '0')} {dados.get('moeda_seguro', '')}"),
            ('Cambio Seguro',       dados.get('cambio_seguro', '')),
            ('Valor Seguro (KZ)',    dados.get('valor_seguro_kz', '')),
            ('Valor Frete',         f"{dados.get('valor_frete', '0')} {dados.get('moeda_frete', '')}"),
            ('Cambio Frete',        dados.get('cambio_frete', '')),
            ('Valor Frete (KZ)',     dados.get('valor_frete_kz', '')),
            ('Forma de Pagamento',  dados.get('forma_pagamento', '')),
        ])
        if t: story.append(t)

        # 6. TRANSPORTE
        titulo_secao('6. TRANSPORTE')
        t = tabela_kv([
            ('Modo de Transporte',   dados.get('modo_transporte', du.meio_transporte or '')),
            ('N Conhecimento',       dados.get('numero_conhecimento', '')),
            ('Data Conhecimento',    dados.get('data_conhecimento', '')),
            ('Porto de Embarque',    dados.get('porto_embarque', du.porto_embarque or '')),
            ('Porto de Desembarque', dados.get('porto_desembarque', du.porto_desembarque or '')),
            ('Pais de Expedicao',    dados.get('pais_expedicao', '')),
            ('Ha Contentores?',      'Sim' if dados.get('tem_contentores') == 'sim' else 'Nao'),
        ])
        if t: story.append(t)

        contentores = dados.get('contentores', [])
        if contentores:
            titulo_secao('6.1. CONTENTORES')
            cont_rows = [['N', 'Identificacao', 'Tipo', 'Peso Bruto', 'Qtd. Volumes']]
            for i, c in enumerate(contentores, 1):
                cont_rows.append([
                    str(i),
                    c.get('identificacao', 'N/D'),
                    c.get('tipo', 'N/D'),
                    c.get('peso_bruto', 'N/D'),
                    c.get('qtd_volumes', 'N/D'),
                ])
            t_cont = Table(cont_rows, colWidths=[0.8*cm, 5*cm, 3*cm, 3*cm, 3*cm])
            t_cont.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(t_cont)

        # 7. ADICOES
        adicoes = dados.get('adicoes', [])
        if adicoes:
            titulo_secao(f'7. ADICOES ({len(adicoes)})')
            for i, ad in enumerate(adicoes, 1):
                story.append(Paragraph(f'Adicao {i}', ParagraphStyle('ad_titulo',
                    fontSize=8.5, fontName='Helvetica-Bold',
                    textColor=cor_primaria, spaceBefore=4, spaceAfter=2)))
                t = tabela_kv([
                    ('Codigo Pautal',        ad.get('codigo_pautal', '')),
                    ('Descricao Mercadoria', ad.get('descricao_mercadoria', '')),
                    ('Pais de Origem',       ad.get('pais_origem', '')),
                    ('Codigo Procedimento',  ad.get('codigo_procedimento', '')),
                    ('Codigo de Isencao',    ad.get('codigo_isencao', '000')),
                    ('Quantidade',           ad.get('quantidade', '')),
                    ('Peso Bruto (kg)',       ad.get('peso_bruto', '')),
                    ('Peso Liquido (kg)',     ad.get('peso_liquido', '')),
                    ('Valor FOB',            f"{ad.get('valor_fob', '0')} {ad.get('moeda_fob', '')}"),
                    ('Valor FOB (KZ)',        ad.get('valor_fob_kz', '')),
                    ('Valor CIF (KZ)',        ad.get('montante_kz', '')),
                    ('Reparticao Seguro',    ad.get('reparticao_seguro', '')),
                    ('Reparticao Frete',     ad.get('reparticao_frete', '')),
                ], col_label=5.5*cm)
                if t: story.append(t)

                impostos = ad.get('impostos', {})
                if impostos:
                    imp_rows = [['Imposto', 'Base (KZ)', 'Taxa (%)', 'Valor (KZ)', 'Accao']]
                    for cod, info in impostos.items():
                        if isinstance(info, dict) and info.get('valor', 0):
                            imp_rows.append([
                                cod,
                                f"{float(info.get('base', 0)):,.2f}",
                                f"{info.get('taxa', 0)}%",
                                f"{float(info.get('valor', 0)):,.2f}",
                                info.get('acao', ''),
                            ])
                    if len(imp_rows) > 1:
                        t_imp = Table(imp_rows, colWidths=[2*cm, 3.5*cm, 2*cm, 3.5*cm, 2.5*cm])
                        t_imp.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
                            ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
                            ('TOPPADDING', (0, 0), (-1, -1), 3),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                            ('LEFTPADDING', (0, 0), (-1, -1), 5),
                            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                        ]))
                        story.append(t_imp)

        # 8. CALCULOS DE TAXACAO
        titulo_secao('8. RESUMO DE TAXACAO')
        totais_rows = [
            [Paragraph('<b>Imposto</b>', s_bold), Paragraph('<b>Valor (KZ)</b>', s_bold)],
            ['DERIMP - Direitos de Importacao',    f'{float(du.total_derimp):,.2f}'],
            ['IEC - Imposto Especial de Consumo',  f'{float(du.total_iec):,.2f}'],
            ['05M - Emolumentos Gerais (EMGEAD)',   f'{float(du.total_emgead):,.2f}'],
            ['DIREXP - Direitos de Exportacao',     f'{float(du.total_direxp):,.2f}'],
            ['IVA',                                 f'{float(du.total_iva):,.2f}'],
        ]
        t_tot = Table(totais_rows, colWidths=[W - 4*cm, 4*cm])
        t_tot.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_tot)

        t_total = Table([[
            Paragraph('<b>TOTAL A PAGAR</b>', ParagraphStyle('tp',
                fontSize=11, fontName='Helvetica-Bold', textColor=colors.white)),
            Paragraph(f'<b>{float(du.total_geral):,.2f} KZ</b>', ParagraphStyle('tv',
                fontSize=11, fontName='Helvetica-Bold', textColor=colors.white, alignment=2)),
        ]], colWidths=[W - 4*cm, 4*cm])
        t_total.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), cor_cabecalho),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_total)

        # 9. VALORES ADUANEIROS
        titulo_secao('9. VALORES ADUANEIROS')
        t = tabela_kv([
            ('Valor FOB (KZ)',    f'{float(du.valor_fob):,.2f}'),
            ('Valor Frete (KZ)', f'{float(du.valor_frete or 0):,.2f}'),
            ('Valor Seguro (KZ)', f'{float(du.valor_seguro or 0):,.2f}'),
            ('Valor CIF (KZ)',    f'{float(du.valor_cif):,.2f}'),
        ])
        if t: story.append(t)

        # 10. ASSINATURA E CARIMBO
        story.append(Spacer(1, 0.8*cm))
        story.append(HRFlowable(width=W, thickness=1, color=cor_borda, spaceAfter=6))
        titulo_secao('10. DECLARACAO E ASSINATURA DO DESPACHANTE')

        data_hoje = timezone.now().strftime('%d/%m/%Y')
        story.append(Paragraph(
            f'Eu, <b>{desp_nome}</b>, portador do NIF <b>{desp_nif}</b>, '
            f'N de Cedula/Licenca <b>{desp_cedula}</b>, na qualidade de <b>{desp_papel}</b>, '
            f'declaro que as informacoes constantes nesta Declaracao Unica sao verdadeiras e '
            f'conformes com os documentos que as suportam, assumindo total responsabilidade '
            f'pelo seu conteudo.',
            ParagraphStyle('declaracao', fontSize=8.5, fontName='Helvetica',
                           textColor=cor_cabecalho, leading=13, spaceAfter=16)
        ))

        assin_data = [[
            Table([
                [Paragraph('Assinatura do Despachante', s_assinatura)],
                [Spacer(1, 1.8*cm)],
                [HRFlowable(width=6.5*cm, thickness=0.8, color=colors.HexColor('#94a3b8'))],
                [Paragraph(f'<b>{desp_nome}</b>', ParagraphStyle('an',
                    fontSize=8, fontName='Helvetica-Bold', textColor=cor_cabecalho))],
                [Paragraph(desp_papel, s_assinatura)],
                [Paragraph(f'Data: {data_hoje}', s_assinatura)],
            ], colWidths=[7*cm]),
            Spacer(1, 0.5*cm),
            Table([
                [Paragraph('Carimbo / Selo', s_assinatura)],
                [Table([['']], colWidths=[6.5*cm], rowHeights=[2.5*cm],
                    style=TableStyle([
                        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                    ]))],
                [Paragraph('(Carimbo da empresa / entidade)', ParagraphStyle('cc',
                    fontSize=7, fontName='Helvetica',
                    textColor=colors.HexColor('#94a3b8'), alignment=1))],
            ], colWidths=[7*cm]),
        ]]
        t_assin = Table(assin_data, colWidths=[7.5*cm, 0.5*cm, 7.5*cm])
        t_assin.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_assin)

        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width=W, thickness=0.5, color=cor_borda, spaceAfter=4))
        story.append(Paragraph(
            f'Documento gerado pelo Sistema CDOA  |  '
            f'DU N {du.numero_du or "Rascunho"}  |  '
            f'Processo: {du.codigo_processo or "N/D"}  |  '
            f'Gerado em: {timezone.now().strftime("%d/%m/%Y %H:%M")}',
            ParagraphStyle('rodape', fontSize=7, fontName='Helvetica',
                           textColor=colors.HexColor('#94a3b8'), alignment=1)
        ))

        doc.build(story)
        buffer.seek(0)

        nome_ficheiro = f'DU_{du.numero_du or du.du_uuid}.pdf'
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{nome_ficheiro}"'
        return response

    except ImportError:
        return HttpResponse(
            'ReportLab nao instalado. Execute: pip install reportlab',
            status=500
        )



def du_pesquisar(request):
    """API JSON — pesquisa DUs por código_processo (4+ dígitos) ou nome do cliente."""
    if not _sessao_ok(request):
        return JsonResponse({'resultados': []})

    q     = request.GET.get('q', '').strip()
    papel = _papel(request)
    uid   = _usuario_id(request)

    if len(q) < 2:
        return JsonResponse({'resultados': []})

    if papel == 'Administrador':
        qs = DeclaracaoUnica.objects.all()
    else:
        qs = DeclaracaoUnica.objects.filter(usuario_id=uid)

    qs = qs.filter(
        Q(codigo_processo__icontains=q) |
        Q(numero_du__icontains=q) |
        Q(exportador_nome__icontains=q) |
        Q(destinatario_nome__icontains=q) |
        Q(nome_declarante__icontains=q) |
        Q(ref_despachante__icontains=q)
    ).order_by('-created_at')[:10]

    resultados = [
        {
            'codigo_processo': du.codigo_processo or '',
            'numero_du':       du.numero_du or 'Rascunho',
            'cliente':         du.exportador_nome or du.nome_declarante or '—',
            'regime':          du.regime_aduaneiro or '—',
            'status':          du.status,
            'url':             f'/du/{du.du_uuid}/ver/',
        }
        for du in qs
    ]
    return JsonResponse({'resultados': resultados})


# ─── APIs de clientes (mantidas) ─────────────────────────────────────────────

def consultar_nif_cliente(request):
    """API para consultar NIF de clientes/exportadores dinamicamente."""
    if not _sessao_ok(request):
        return JsonResponse({'error': 'Não autorizado'}, status=401)

    nif = request.GET.get('nif', '').strip()
    if not nif:
        return JsonResponse({'error': 'NIF não fornecido'}, status=400)

    try:
        uid = _usuario_id(request)

        # 1. Procura exacta no próprio utilizador
        if len(nif) >= 4:
            cliente = Cliente.objects.filter(
                Q(nif__iexact=nif) & Q(usuario_id=uid) & Q(ativo=True)
            ).first()
            if cliente:
                return JsonResponse({'encontrado': True, 'dados': {
                    'nome': cliente.nome, 'nif': cliente.nif,
                    'endereco': cliente.localizacao,
                    'telefone': cliente.telefone or '',
                    'email': cliente.email or '',
                }})

        # 2. Procura exacta em todos os clientes (qualquer utilizador)
        if len(nif) >= 4:
            cliente = Cliente.objects.filter(
                Q(nif__iexact=nif) & Q(ativo=True)
            ).first()
            if cliente:
                return JsonResponse({'encontrado': True, 'dados': {
                    'nome': cliente.nome, 'nif': cliente.nif,
                    'endereco': cliente.localizacao,
                    'telefone': cliente.telefone or '',
                    'email': cliente.email or '',
                }})

        # 3. Sugestões parciais no próprio utilizador
        if len(nif) >= 3:
            sugestoes = Cliente.objects.filter(
                Q(nif__icontains=nif) & Q(usuario_id=uid) & Q(ativo=True)
            ).values('id', 'nome', 'nif', 'localizacao', 'telefone', 'email')[:8]
            if sugestoes:
                return JsonResponse({
                    'encontrado': False,
                    'sugestoes': list(sugestoes),
                    'mensagem': f'NIF {nif} não encontrado. Sugestões:',
                })

        # 4. Não encontrado — retornar erro sem permitir criação
        return JsonResponse({
            'encontrado': False,
            'sugestoes': [],
            'mensagem': f'Nenhum cliente encontrado com o NIF {nif}. Por favor, verifique o NIF ou crie o cliente na seção de Clientes.',
            'mostrar_formulario': False,
        })

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


def criar_cliente_rapido(request):
    """API para criar cliente rapidamente via AJAX."""
    if not _sessao_ok(request):
        return JsonResponse({'error': 'Não autorizado'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'error': 'Método não permitido'}, status=405)

    try:
        uid        = _usuario_id(request)
        nome       = request.POST.get('nome', '').strip()
        nif        = request.POST.get('nif', '').strip()
        localizacao = request.POST.get('localizacao', '').strip()
        telefone   = request.POST.get('telefone', '').strip()
        email      = request.POST.get('email', '').strip()
        observacoes = request.POST.get('observacoes', '').strip()

        if not nome or not nif or not localizacao:
            return JsonResponse({'error': 'Nome, NIF e Localização são obrigatórios'}, status=400)

        if Cliente.objects.filter(nif=nif, usuario_id=uid, ativo=True).exists():
            return JsonResponse({'error': 'Já existe um cliente com este NIF'}, status=400)

        if email and email_ja_existe(email):
            return JsonResponse({'error': 'Este email já está registado no sistema.'}, status=400)

        cliente = Cliente.objects.create(
            nome=nome, nif=nif, localizacao=localizacao,
            telefone=telefone, email=email, observacoes=observacoes,
            usuario_id=uid, ativo=True,
        )
        return JsonResponse({'sucesso': True, 'cliente': {
            'nome': cliente.nome, 'nif': cliente.nif,
            'endereco': cliente.localizacao,
            'telefone': cliente.telefone or '',
            'email': cliente.email or '',
        }, 'mensagem': f'Cliente "{nome}" criado com sucesso!'})

    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=500)


# ─── Pauta Aduaneira ────────────────────────────────────────────────────────

def pauta_aduaneira_view(request):
    """Página de consulta da pauta aduaneira."""
    if not _sessao_ok(request):
        return redirect('login')

    ctx = _ctx_base(request)
    ctx.update({
        'active_menu': 'Gestão Aduaneira',
        'active_sub': 'pauta_aduaneira',
    })
    return render(request, 'pauta_aduaneira.html', ctx)


# Dados base da Pauta Aduaneira de Angola (Sistema Harmonizado)
_PAUTA_BASE = [
    # Cap 01 — Animais vivos
    ('01011000', 'Cavalos reprodutores de raça pura', 0, 0, 'UN'),
    ('01012100', 'Cavalos para reprodução', 2, 0, 'UN'),
    ('01012900', 'Outros cavalos', 5, 0, 'UN'),
    ('01013000', 'Asininos (burros)', 5, 0, 'UN'),
    ('01022100', 'Bovinos reprodutores de raça pura', 0, 0, 'UN'),
    ('01022900', 'Outros bovinos vivos', 10, 0, 'UN'),
    ('01031000', 'Suínos reprodutores de raça pura', 0, 0, 'UN'),
    ('01039100', 'Suínos com peso inferior a 50 kg', 15, 0, 'UN'),
    ('01039200', 'Suínos com peso igual ou superior a 50 kg', 15, 0, 'UN'),
    ('01041000', 'Ovinos vivos', 5, 0, 'UN'),
    ('01042000', 'Caprinos vivos', 5, 0, 'UN'),
    ('01051100', 'Galinhas e galos domésticos', 2, 0, 'UN'),
    ('01051200', 'Perus e peruas', 2, 0, 'UN'),
    ('01051300', 'Patos', 2, 0, 'UN'),
    ('01051400', 'Gansos', 2, 0, 'UN'),
    ('01051900', 'Outras aves domésticas vivas', 5, 0, 'UN'),
    ('01061100', 'Primatas vivos', 0, 0, 'UN'),
    ('01061300', 'Camelos e outros camelídeos', 5, 0, 'UN'),
    ('01061400', 'Coelhos e lebres', 5, 0, 'UN'),
    # Cap 02 — Carnes e miudezas
    ('02011000', 'Carcaças e meias-carcaças de bovino, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02012000', 'Outros cortes não desossados de bovino, frescos ou refrigerados', 20, 0, 'KG'),
    ('02013000', 'Carnes desossadas de bovino, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02021000', 'Carcaças e meias-carcaças de bovino, congeladas', 20, 0, 'KG'),
    ('02022000', 'Outros cortes não desossados de bovino, congelados', 20, 0, 'KG'),
    ('02023000', 'Carnes desossadas de bovino, congeladas', 20, 0, 'KG'),
    ('02031100', 'Carcaças e meias-carcaças de suíno, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02031200', 'Pernas, pás e pedaços de suíno, frescos ou refrigerados', 20, 0, 'KG'),
    ('02031900', 'Outras carnes de suíno, frescas ou refrigeradas', 20, 0, 'KG'),
    ('02032100', 'Carcaças e meias-carcaças de suíno, congeladas', 20, 0, 'KG'),
    ('02032200', 'Pernas, pás e pedaços de suíno, congelados', 20, 0, 'KG'),
    ('02032900', 'Outras carnes de suíno, congeladas', 20, 0, 'KG'),
    ('02071100', 'Frangos inteiros, frescos ou refrigerados', 30, 0, 'KG'),
    ('02071200', 'Frangos inteiros, congelados', 30, 0, 'KG'),
    ('02071300', 'Pedaços e miudezas de frango, frescos ou refrigerados', 30, 0, 'KG'),
    ('02071400', 'Pedaços e miudezas de frango, congelados', 30, 0, 'KG'),
    # Cap 03 — Peixes e crustáceos
    ('03011100', 'Trutas vivas', 5, 0, 'KG'),
    ('03011900', 'Outros peixes de água doce vivos', 5, 0, 'KG'),
    ('03024100', 'Atuns de barbatana amarela, frescos ou refrigerados', 10, 0, 'KG'),
    ('03025100', 'Arenques frescos ou refrigerados', 10, 0, 'KG'),
    ('03026100', 'Sardinhas frescas ou refrigeradas', 10, 0, 'KG'),
    ('03036300', 'Sardinhas congeladas', 10, 0, 'KG'),
    ('03037100', 'Atuns de barbatana amarela, congelados', 10, 0, 'KG'),
    ('03061100', 'Lagostas congeladas', 5, 0, 'KG'),
    ('03061700', 'Camarões congelados', 5, 0, 'KG'),
    # Cap 04 — Lacticínios
    ('04011000', 'Leite e nata, não concentrados, teor de gordura <= 1%', 5, 0, 'LT'),
    ('04012000', 'Leite e nata, não concentrados, teor de gordura > 1% e <= 6%', 5, 0, 'LT'),
    ('04021000', 'Leite em pó, teor de gordura <= 1,5%', 5, 0, 'KG'),
    ('04022100', 'Leite em pó, teor de gordura > 1,5%, sem adição de açúcar', 5, 0, 'KG'),
    ('04031000', 'Iogurte', 20, 0, 'KG'),
    ('04051000', 'Manteiga', 20, 0, 'KG'),
    ('04061000', 'Queijo fresco (não curado)', 20, 0, 'KG'),
    ('04062000', 'Queijo ralado ou em pó', 20, 0, 'KG'),
    ('04063000', 'Queijo fundido', 20, 0, 'KG'),
    ('04069000', 'Outros queijos', 20, 0, 'KG'),
    # Cap 09 — Café, chá, especiarias
    ('09011100', 'Café não torrado, não descafeinado', 0, 0, 'KG'),
    ('09011200', 'Café não torrado, descafeinado', 0, 0, 'KG'),
    ('09012100', 'Café torrado, não descafeinado', 20, 0, 'KG'),
    ('09012200', 'Café torrado, descafeinado', 20, 0, 'KG'),
    ('09021000', 'Chá verde (não fermentado), em embalagens <= 3 kg', 20, 0, 'KG'),
    ('09023000', 'Chá preto (fermentado), em embalagens <= 3 kg', 20, 0, 'KG'),
    ('09030000', 'Mate', 10, 0, 'KG'),
    ('09041100', 'Pimenta do género Piper, não triturada nem em pó', 20, 0, 'KG'),
    ('09041200', 'Pimenta do género Piper, triturada ou em pó', 20, 0, 'KG'),
    ('09051000', 'Baunilha, não triturada nem em pó', 10, 0, 'KG'),
    ('09061100', 'Canela e flores de caneleira, não trituradas nem em pó', 20, 0, 'KG'),
    ('09070000', 'Cravinho (frutos e pedúnculos)', 20, 0, 'KG'),
    ('09081100', 'Noz-moscada, não triturada nem em pó', 20, 0, 'KG'),
    ('09101100', 'Gengibre, não triturado nem em pó', 20, 0, 'KG'),
    ('09102000', 'Açafrão', 20, 0, 'KG'),
    ('09103000', 'Cúrcuma (açafrão-da-terra)', 20, 0, 'KG'),
    # Cap 10 — Cereais
    ('10011100', 'Trigo duro para sementeira', 2, 0, 'KG'),
    ('10011900', 'Outro trigo duro', 5, 0, 'KG'),
    ('10019900', 'Outro trigo mole e mistura de trigo e centeio', 5, 0, 'KG'),
    ('10030000', 'Cevada', 5, 0, 'KG'),
    ('10040000', 'Aveia', 5, 0, 'KG'),
    ('10051000', 'Milho para sementeira', 2, 0, 'KG'),
    ('10059000', 'Outro milho', 5, 0, 'KG'),
    ('10061000', 'Arroz em casca (arroz paddy)', 5, 0, 'KG'),
    ('10062000', 'Arroz descascado (arroz cargo ou castanho)', 5, 0, 'KG'),
    ('10063000', 'Arroz semibranqueado ou branqueado', 10, 0, 'KG'),
    ('10064000', 'Arroz partido', 10, 0, 'KG'),
    ('10070000', 'Sorgo de grão', 5, 0, 'KG'),
    ('10082900', 'Milho-miúdo', 5, 0, 'KG'),
    # Cap 22 — Bebidas
    ('22011000', 'Águas minerais e águas gaseificadas', 5, 0, 'LT'),
    ('22019000', 'Outras águas e gelo', 5, 0, 'LT'),
    ('22021000', 'Água, incluindo a mineral e a gaseificada, adicionada de açúcar', 20, 0, 'LT'),
    ('22029000', 'Outras bebidas não alcoólicas', 20, 0, 'LT'),
    ('22030000', 'Cerveja de malte', 30, 30, 'LT'),
    ('22041000', 'Champanhe e outros vinhos espumantes', 30, 30, 'LT'),
    ('22042100', 'Outros vinhos em recipientes <= 2 litros', 30, 30, 'LT'),
    ('22071000', 'Álcool etílico não desnaturado, teor alcoólico >= 80%', 30, 50, 'LT'),
    ('22082000', 'Aguardentes de vinho ou de bagaço de uvas', 30, 50, 'LT'),
    ('22083000', 'Uísque', 30, 50, 'LT'),
    ('22084000', 'Rum e tafia', 30, 50, 'LT'),
    ('22085000', 'Gin e genebra', 30, 50, 'LT'),
    ('22086000', 'Vodca', 30, 50, 'LT'),
    ('22089000', 'Outras bebidas espirituosas', 30, 50, 'LT'),
    # Cap 24 — Tabaco
    ('24011000', 'Tabaco não destalado', 30, 0, 'KG'),
    ('24012000', 'Tabaco total ou parcialmente destalado', 30, 0, 'KG'),
    ('24021000', 'Charutos e cigarrilhas, contendo tabaco', 30, 150, 'UN'),
    ('24022000', 'Cigarros contendo tabaco', 30, 150, 'UN'),
    ('24031100', 'Tabaco para cachimbo de água', 30, 100, 'KG'),
    # Cap 27 — Combustíveis minerais
    ('27090000', 'Óleos brutos de petróleo ou de minerais betuminosos', 0, 0, 'LT'),
    ('27101200', 'Gasolinas para motores', 5, 0, 'LT'),
    ('27101900', 'Outros óleos de petróleo leves', 5, 0, 'LT'),
    ('27102000', 'Óleos de petróleo contendo biodiesel', 5, 0, 'LT'),
    ('27111100', 'Gás natural liquefeito', 5, 0, 'KG'),
    ('27112100', 'Gás natural em estado gasoso', 5, 0, 'KG'),
    # Cap 30 — Produtos farmacêuticos
    ('30021000', 'Antissoros e outros componentes do sangue', 0, 0, 'KG'),
    ('30022000', 'Vacinas para medicina humana', 0, 0, 'KG'),
    ('30023000', 'Vacinas para medicina veterinária', 0, 0, 'KG'),
    ('30031000', 'Medicamentos contendo penicilinas ou estreptomicinas', 0, 0, 'KG'),
    ('30032000', 'Medicamentos contendo antibióticos', 0, 0, 'KG'),
    ('30039000', 'Outros medicamentos', 0, 0, 'KG'),
    ('30041000', 'Medicamentos contendo penicilinas, em doses', 0, 0, 'KG'),
    ('30049000', 'Outros medicamentos em doses', 0, 0, 'KG'),
    # Cap 84 — Máquinas e aparelhos mecânicos
    ('84071000', 'Motores de pistão para aviação', 5, 0, 'UN'),
    ('84072100', 'Motores fora de borda para embarcações', 10, 0, 'UN'),
    ('84073100', 'Motores de pistão para veículos, cilindrada <= 50 cm3', 10, 0, 'UN'),
    ('84073200', 'Motores de pistão para veículos, cilindrada > 50 cm3 e <= 250 cm3', 10, 0, 'UN'),
    ('84073300', 'Motores de pistão para veículos, cilindrada > 250 cm3 e <= 1000 cm3', 10, 0, 'UN'),
    ('84073400', 'Motores de pistão para veículos, cilindrada > 1000 cm3', 10, 0, 'UN'),
    ('84081000', 'Motores diesel para aviação', 5, 0, 'UN'),
    ('84082000', 'Motores diesel para veículos', 10, 0, 'UN'),
    ('84431100', 'Máquinas de impressão offset, de alimentação em bobinas', 5, 0, 'UN'),
    ('84713000', 'Máquinas de processamento de dados portáteis (laptops)', 5, 0, 'UN'),
    ('84714100', 'Outras máquinas de processamento de dados, com unidade central', 5, 0, 'UN'),
    ('84716000', 'Unidades de entrada ou saída de dados', 5, 0, 'UN'),
    # Cap 85 — Máquinas e aparelhos elétricos
    ('85011000', 'Motores de potência <= 37,5 W', 5, 0, 'UN'),
    ('85012000', 'Motores universais de potência > 37,5 W', 5, 0, 'UN'),
    ('85044000', 'Conversores estáticos (carregadores, inversores)', 10, 0, 'UN'),
    ('85176200', 'Aparelhos para recepção, conversão e transmissão de voz/dados', 10, 0, 'UN'),
    ('85177000', 'Partes de aparelhos de telefonia', 10, 0, 'UN'),
    ('85211000', 'Aparelhos de gravação ou reprodução de vídeo', 20, 0, 'UN'),
    ('85258000', 'Câmaras de televisão, câmaras digitais e câmaras de vídeo', 20, 0, 'UN'),
    ('85271200', 'Rádios para veículos automóveis', 20, 0, 'UN'),
    ('85272100', 'Rádios portáteis', 20, 0, 'UN'),
    ('85281200', 'Monitores de televisão a cores', 20, 0, 'UN'),
    ('85287200', 'Outros aparelhos receptores de televisão a cores', 20, 0, 'UN'),
    # Cap 87 — Veículos automóveis
    ('87011000', 'Motocultores', 5, 0, 'UN'),
    ('87012000', 'Tractores rodoviários para semi-reboques', 5, 0, 'UN'),
    ('87019000', 'Outros tractores', 5, 0, 'UN'),
    ('87021000', 'Veículos para transporte de 10 ou mais pessoas, motor diesel', 5, 0, 'UN'),
    ('87029000', 'Outros veículos para transporte de 10 ou mais pessoas', 5, 0, 'UN'),
    ('87031000', 'Veículos especialmente concebidos para deslocação na neve', 10, 0, 'UN'),
    ('87032100', 'Automóveis de cilindrada <= 1000 cm3', 30, 0, 'UN'),
    ('87032200', 'Automóveis de cilindrada > 1000 cm3 e <= 1500 cm3', 30, 0, 'UN'),
    ('87032300', 'Automóveis de cilindrada > 1500 cm3 e <= 3000 cm3', 30, 0, 'UN'),
    ('87032400', 'Automóveis de cilindrada > 3000 cm3', 30, 0, 'UN'),
    ('87033100', 'Automóveis diesel de cilindrada <= 1500 cm3', 30, 0, 'UN'),
    ('87033200', 'Automóveis diesel de cilindrada > 1500 cm3 e <= 2500 cm3', 30, 0, 'UN'),
    ('87033300', 'Automóveis diesel de cilindrada > 2500 cm3', 30, 0, 'UN'),
    ('87042100', 'Veículos para transporte de mercadorias, diesel, <= 5 ton', 10, 0, 'UN'),
    ('87042200', 'Veículos para transporte de mercadorias, diesel, > 5 ton', 10, 0, 'UN'),
    ('87051000', 'Veículos-grua', 5, 0, 'UN'),
    ('87060000', 'Chassis com motor para veículos automóveis', 10, 0, 'UN'),
    ('87089900', 'Outras partes e acessórios de veículos automóveis', 20, 0, 'UN'),
    # Cap 90 — Instrumentos e aparelhos de óptica
    ('90181100', 'Electrocardiógrafos', 0, 0, 'UN'),
    ('90181200', 'Aparelhos de diagnóstico por ultrassom', 0, 0, 'UN'),
    ('90181300', 'Aparelhos de diagnóstico por ressonância magnética', 0, 0, 'UN'),
    ('90181400', 'Aparelhos de cintilografia', 0, 0, 'UN'),
    ('90181900', 'Outros aparelhos de electro-diagnóstico', 0, 0, 'UN'),
    ('90192000', 'Aparelhos de ozonioterapia, oxigenoterapia, aerossolterapia', 0, 0, 'UN'),
    ('90211000', 'Artigos e aparelhos de ortopedia', 0, 0, 'UN'),
    ('90213100', 'Articulações artificiais', 0, 0, 'UN'),
    ('90214000', 'Aparelhos para facilitar a audição dos surdos', 0, 0, 'UN'),
]


def pauta_aduaneira_api(request):
    """API de pesquisa da pauta aduaneira — busca dados reais da API externa."""
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)

    q_codigo    = request.GET.get('codigo',    '').strip().upper()
    q_descricao = request.GET.get('descricao', '').strip().lower()
    q_capitulo  = request.GET.get('capitulo',  '').strip()

    try:
        import ssl
        import urllib.request as _urllib
        from utils.ssl_utils import ssl_context_relaxado
        api_url = 'https://api-sic-fields.netsulwel.tech/pautas'

        req = _urllib.Request(
            api_url,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            }
        )
        with _urllib.urlopen(req, timeout=15, context=ssl_context_relaxado()) as resp:
            dados_api = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Erro ao carregar pauta aduaneira: {e}')
        dados_api = []

    # Filtrar e normalizar
    resultados = []
    for item in dados_api:
        # Ignorar itens inactivos
        if not item.get('ativo', True):
            continue

        codigo    = str(item.get('codigo_sh', '') or '').strip()
        descricao = str(item.get('descricao_mercadoria', '') or '').strip()
        aliquota  = item.get('direito_importacao', 0) or 0
        iec       = item.get('direito_consumo', 0) or 0
        iva       = item.get('iva', 0) or 0
        unidade   = str(item.get('unidade_medida', 'UN') or 'UN').strip()
        cap_num   = item.get('capitulo', '')
        cap_str   = str(cap_num).zfill(2) if cap_num else ''
        fonte     = str(item.get('fonte', '') or '').strip()
        obs       = str(item.get('observacoes', '') or '').strip()

        # Aplicar filtros
        if q_codigo and q_codigo not in codigo.upper():
            continue
        if q_descricao and q_descricao not in descricao.lower():
            continue
        if q_capitulo and cap_str != q_capitulo.zfill(2):
            continue

        resultados.append({
            'codigo':    codigo,
            'descricao': descricao,
            'aliquota':  aliquota,
            'iec':       iec,
            'iva':       iva,
            'unidade':   unidade,
            'capitulo':  cap_str,
            'fonte':     fonte,
            'obs':       obs,
        })

    # Ordenar por código
    resultados.sort(key=lambda x: x['codigo'])

    tem_filtro = bool(q_codigo or q_descricao or q_capitulo)

    # Sem filtros — devolver apenas os primeiros 5
    if not tem_filtro:
        resultados = resultados[:5]

    return JsonResponse({'resultados': resultados, 'total': len(resultados)})


# ─── API de Vinhetas (proxy ao portal CDOA) ──────────────────────────────────

def api_vinhetas(request):
    """
    Proxy ao endpoint do portal CDOA para buscar as vinhetas do utilizador autenticado.
    Usa a cédula guardada na sessão para filtrar as vinhetas desse utilizador.
    Devolve apenas vinhetas com status_utilizacao == 'NAO_UTILIZADO'.
    """
    if not _sessao_ok(request):
        return JsonResponse({'erro': 'Não autorizado'}, status=401)

    # Obter a cédula do utilizador da sessão
    usuario_sessao = request.session.get('usuario', {})
    cedula = usuario_sessao.get('cedula', '').strip()

    if not cedula:
        # Tentar buscar directamente da base de dados
        try:
            uid = _usuario_id(request)
            u = Usuario.objects.get(id=uid)
            cedula = (u.cedula or '').strip()
        except Usuario.DoesNotExist:
            pass

    if not cedula:
        return JsonResponse({
            'erro': 'Cédula não configurada no perfil. Por favor, actualize o seu perfil.',
            'vinhetas': [],
        }, status=400)

    import urllib.request as _urllib_req
    import urllib.error as _urllib_err
    from utils.ssl_utils import ssl_context_relaxado

    portal_url = 'https://portal.cdoangola.co.ao/controllers/sicdoa-vinhetas.php'
    payload = json.dumps({'cedula': cedula}).encode('utf-8')

    try:
        req = _urllib_req.Request(
            portal_url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': 'SICDOA/1.0',
            },
            method='POST',
        )
        with _urllib_req.urlopen(req, timeout=15, context=ssl_context_relaxado()) as resp:
            dados = json.loads(resp.read().decode('utf-8'))

    except _urllib_err.HTTPError as exc:
        # 404 ou qualquer HTTP error — mensagem amigável
        if exc.code == 404:
            return JsonResponse({
                'sem_vinhetas': True,
                'mensagem': 'Nenhuma vinheta disponível para a sua cédula.',
                'vinhetas': [],
            })
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })
    except _urllib_err.URLError:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Não foi possível contactar o portal CDOA. Verifique a sua ligação.',
            'vinhetas': [],
        })
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })
    except Exception:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível.',
            'vinhetas': [],
        })

    # Verificar status da resposta do portal (404 lógico ou utilizador não encontrado)
    if dados.get('status') != 200:
        return JsonResponse({
            'sem_vinhetas': True,
            'mensagem': 'Nenhuma vinheta disponível para a sua cédula.',
            'vinhetas': [],
        })

    # Filtrar apenas vinhetas não utilizadas
    todas_vinhetas = dados.get('vinhetas', [])
    vinhetas_disponiveis = [
        v for v in todas_vinhetas
        if v.get('status_utilizacao') == 'NAO_UTILIZADO' and v.get('estado') == '1'
    ]

    despachante = dados.get('despachante', {})

    return JsonResponse({
        'sucesso': True,
        'cedula': cedula,
        'despachante': {
            'nome': f"{despachante.get('nome', '')} {despachante.get('apelido', '')}".strip(),
            'nif': despachante.get('nif', ''),
        },
        'total_vinhetas': dados.get('total_vinhetas', 0),
        'total_disponiveis': len(vinhetas_disponiveis),
        'vinhetas': [
            {
                'id': v.get('id'),
                'vinheta': v.get('vinheta', ''),
                'valor': v.get('valor', 0),
                'created_at': v.get('created_at', ''),
            }
            for v in vinhetas_disponiveis
        ],
    })
