"""
views_agt.py — Faturação Eletrónica AGT
Gestão e acompanhamento de faturas validadas pela AGT (Administração Geral Tributária)

Integração segundo DOMENTACAO_AGT.md:
  - Autenticação: HTTP Basic Auth (username:password em Base64)
  - Assinaturas: JWS RS256 via agt_crypto.py
  - URL homologação: https://sifphml.minfin.gov.ao/sigt/fe/v1/
  - Processamento assíncrono: submete → obtém requestID → polling
"""
import json
import logging

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from users.auth_decorators import requer_sessao_ativa
from .views import requer_escrita_financeira
from .models import FaturaAGT, FacturaCliente
from .agt_crypto import construir_payload_agt, gerar_request_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração da API AGT
# ---------------------------------------------------------------------------

# URL pública do nosso webhook callback
CALLBACK_URL = getattr(settings, 'AGT_CALLBACK_URL', 'https://sicdoa.cdoangola.co.ao/api/facturacaoelectronica/callback')

# Base URL da API AGT — usa homologação por defeito; em produção definir
# AGT_API_BASE = "https://sifp.minfin.gov.ao/sigt/fe/v1" no settings/.env
AGT_API_BASE = getattr(settings, 'AGT_API_BASE', 'https://sifphml.minfin.gov.ao/sigt/fe/v1')


def _agt_session():
    """
    Cria uma requests.Session com Basic Auth configurado.
    Credenciais definidas em settings (via .env):
        AGT_USERNAME — username emitido pela AGT
        AGT_PASSWORD — password emitida pela AGT
    """
    import requests as req
    from requests.auth import HTTPBasicAuth

    username = getattr(settings, 'AGT_USERNAME', '')
    password = getattr(settings, 'AGT_PASSWORD', '')

    session = req.Session()
    session.headers.update({
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    })
    if username:
        session.auth = HTTPBasicAuth(username, password)
    else:
        logger.warning(
            'AGT_USERNAME não configurado — chamadas à AGT sem autenticação. '
            'Definir AGT_USERNAME e AGT_PASSWORD no .env para ambiente real.'
        )
    return session


def _submeter_para_agt(fatura: FaturaAGT) -> dict:
    """
    Submete a fatura à API AGT.
    Endpoint: POST /sigt/fe/v1/registarFactura
    Devolve o dict da resposta AGT ou lança excepção.
    """
    payload = construir_payload_agt(fatura)

    # Guardar o requestID gerado no campo da fatura antes de enviar
    request_id = payload.get('requestID', '')

    session = _agt_session()
    response = session.post(
        f'{AGT_API_BASE}/registarFactura',
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    # A AGT devolve requestID imediatamente (processamento assíncrono)
    return {'request_id': request_id, 'agt_response': data}


def _consultar_status_agt(agt_id: str) -> dict:
    """
    Consulta o status de processamento via polling.
    Endpoint: GET /sigt/fe/v1/consultarFactura/{agt_id}
    """
    session = _agt_session()
    response = session.get(
        f'{AGT_API_BASE}/consultarFactura/{agt_id}',
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@requer_sessao_ativa
def faturacao_agt_dashboard(request):
    """Dashboard principal da Faturação Eletrónica AGT."""
    banca_id = request.session.get('banca_id')
    qs = FaturaAGT.objects.all()
    if banca_id:
        qs = qs.filter(banca_id=banca_id)

    total_pendentes = qs.filter(agt_status='Pendente').count()
    total_emitidas = qs.count()
    total_validadas = qs.filter(agt_status='Validada').count()
    total_rejeitadas = qs.filter(agt_status='Rejeitada').count()
    total_processando = qs.filter(agt_status='Processando').count()

    taxa_validacao = 0
    if total_emitidas > 0:
        taxa_validacao = round((total_validadas / total_emitidas) * 100, 1)

    faturas_recentes = qs.select_related('factura').order_by('-data_emissao')[:5]

    # Avisos de configuração (apenas para admins/despachantes)
    alertas_config = []
    if not getattr(settings, 'AGT_USERNAME', ''):
        alertas_config.append('AGT_USERNAME não configurado no .env — credenciais AGT em falta.')
    if not getattr(settings, 'AGT_SOFTWARE_VALIDATION_NUMBER', ''):
        alertas_config.append('AGT_SOFTWARE_VALIDATION_NUMBER não configurado — número de validação do software AGT em falta.')
    if not getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY', '') and not getattr(settings, 'AGT_SOFTWARE_PRIVATE_KEY_FILE', ''):
        alertas_config.append('Chave privada do produtor (AGT_SOFTWARE_PRIVATE_KEY) não configurada — a usar chave efémera de desenvolvimento.')
    if not getattr(settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY', '') and not getattr(settings, 'AGT_CONTRIBUTOR_PRIVATE_KEY_FILE', ''):
        alertas_config.append('Chave privada do contribuinte (AGT_CONTRIBUTOR_PRIVATE_KEY) não configurada — a usar chave efémera de desenvolvimento.')

    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_agt',
        'sub': 'faturacao_agt',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'total_pendentes': total_pendentes,
        'total_emitidas': total_emitidas,
        'total_validadas': total_validadas,
        'total_rejeitadas': total_rejeitadas,
        'total_processando': total_processando,
        'taxa_validacao': taxa_validacao,
        'faturas_recentes': faturas_recentes,
        'callback_url': CALLBACK_URL,
        'agt_api_base': AGT_API_BASE,
        'alertas_config': alertas_config,
        'agt_configurado': not bool(alertas_config),
    }
    return render(request, 'financeiro/faturacao_agt_dashboard.html', context)


@requer_sessao_ativa
def faturacao_agt_lista(request):
    """Lista paginada de faturas AGT com filtros."""
    banca_id = request.session.get('banca_id')
    status = request.GET.get('status', '')
    busca = request.GET.get('busca', '')

    qs = FaturaAGT.objects.all()
    if banca_id:
        qs = qs.filter(banca_id=banca_id)
    if status:
        qs = qs.filter(agt_status=status)
    if busca:
        qs = qs.filter(
            Q(numero_fatura__icontains=busca) | Q(nome_cliente__icontains=busca) | Q(nif_cliente__icontains=busca)
        )

    qs = qs.order_by('-data_emissao')
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_agt',
        'sub': 'faturacao_agt',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'faturas': page_obj,
        'page_obj': page_obj,
        'status': status,
        'busca': busca,
        'status_choices': FaturaAGT.STATUS_AGT,
    }
    return render(request, 'financeiro/faturacao_agt_lista.html', context)


@requer_sessao_ativa
def faturacao_agt_detalhe(request, pk):
    """Detalhe de uma fatura AGT — isolado por banca."""
    banca_id = request.session.get('banca_id')
    # Isolamento: só mostra faturas da banca do utilizador
    lookup = {'pk': pk}
    if banca_id:
        lookup['banca_id'] = banca_id
    fatura = get_object_or_404(FaturaAGT, **lookup)
    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_agt',
        'sub': 'faturacao_agt',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'fatura': fatura,
        'resposta_json': json.dumps(fatura.agt_resposta_raw, indent=2, ensure_ascii=False) if fatura.agt_resposta_raw else '',
    }
    return render(request, 'financeiro/faturacao_agt_detalhe.html', context)


@requer_sessao_ativa
@require_POST
@requer_escrita_financeira
def faturacao_agt_submeter(request, factura_pk):
    """
    Submete uma FacturaCliente para validação na AGT.
    Fluxo:
      1. Cria/actualiza FaturaAGT vinculada
      2. Constrói payload com 3 assinaturas JWS (via agt_crypto.py)
      3. POST para /sigt/fe/v1/registarFactura com Basic Auth
      4. Armazena requestID e resposta raw
      5. Redireciona para detalhe da fatura AGT
    """
    factura = get_object_or_404(FacturaCliente, pk=factura_pk)
    # Verificar que a factura pertence à banca do utilizador
    banca_id = request.session.get('banca_id')
    if banca_id and getattr(factura, 'banca_id', None) and str(factura.banca_id) != str(banca_id):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('A factura seleccionada não pertence à sua banca.')
    usuario = request.session.get('usuario', {})

    # Obter NIF do emitente a partir da banca ou da configuração
    nif_emitente = ''
    if hasattr(factura, 'banca') and factura.banca:
        nif_emitente = getattr(factura.banca, 'nif', '') or ''
    if not nif_emitente:
        nif_emitente = getattr(settings, 'AGT_NIF_EMITENTE', '') or ''

    fatura, created = FaturaAGT.objects.get_or_create(
        factura=factura,
        defaults={
            'banca_id': request.session.get('banca_id'),
            'nif_emitente': nif_emitente,
            'nif_cliente': getattr(factura.cliente, 'nif', '') if factura.cliente else '',
            'nome_cliente': getattr(factura.cliente, 'nome', '') if factura.cliente else '',
            'descricao': getattr(factura, 'descricao', '') or 'Serviços de Despacho Aduaneiro',
            'valor_total': factura.valor_total,
            'valor_iva': getattr(factura, 'iva', 0) or 0,
            'valor_sem_iva': factura.valor_total - (getattr(factura, 'iva', 0) or 0),
            'taxa_iva': 14,
            'serie': getattr(settings, 'AGT_SERIE_PADRAO', 'A'),
            'criado_por_id': request.session.get('usuario_id'),
            'criado_por_nome': usuario.get('nome', ''),
        }
    )

    if not created:
        # Actualizar campos se a fatura já existia
        fatura.nif_emitente = nif_emitente or fatura.nif_emitente
        if factura.cliente:
            fatura.nif_cliente = getattr(factura.cliente, 'nif', '') or fatura.nif_cliente
            fatura.nome_cliente = getattr(factura.cliente, 'nome', '') or fatura.nome_cliente
        fatura.valor_total = factura.valor_total
        fatura.valor_iva = getattr(factura, 'iva', 0) or fatura.valor_iva

    fatura.agt_status = 'Processando'
    fatura.agt_motivo_rejeicao = ''
    fatura.save()

    try:
        result = _submeter_para_agt(fatura)
        agt_response = result.get('agt_response', {})
        request_id = result.get('request_id', '')

        # A AGT devolve um ID de rastreio e eventualmente o status inicial
        fatura.agt_id = (
            agt_response.get('requestID')
            or agt_response.get('id')
            or request_id
        )
        fatura.agt_hash = agt_response.get('hash', '')
        fatura.agt_qr_code = agt_response.get('qrCode', '') or agt_response.get('qr_code', '')
        fatura.agt_resposta_raw = agt_response

        # Se a AGT já devolveu status final
        status_agt = agt_response.get('status', 'Processando')
        if status_agt in dict(FaturaAGT.STATUS_AGT):
            fatura.agt_status = status_agt
        else:
            fatura.agt_status = 'Processando'

        if fatura.agt_status == 'Validada':
            fatura.agt_data_validacao = timezone.now()

        fatura.save()
        messages.success(request, f'Fatura {fatura.numero_fatura} submetida à AGT com sucesso. Status: {fatura.agt_status}')

    except Exception as exc:
        logger.error('Erro ao submeter fatura AGT pk=%s: %s', fatura.pk, exc, exc_info=True)
        fatura.agt_status = 'Erro'
        fatura.agt_motivo_rejeicao = str(exc)
        fatura.agt_resposta_raw = {'erro': str(exc)}
        fatura.save()
        messages.error(request, f'Erro ao submeter à AGT: {exc}')

    return redirect(reverse('financeiro:faturacao_agt_detalhe', args=[fatura.pk]))


@requer_sessao_ativa
@require_POST
def faturacao_agt_sincronizar(request, pk):
    """
    Polling: consulta o status actualizado da fatura na AGT.
    Endpoint: GET /sigt/fe/v1/consultarFactura/{agt_id}
    Aceita apenas POST para prevenir GET-based state mutation.
    Devolve JSON com o status actualizado.
    """
    try:
        banca_id = request.session.get('banca_id')
        # Isolamento: só sincroniza faturas da banca do utilizador
        lookup = {'pk': pk}
        if banca_id:
            lookup['banca_id'] = banca_id
        fatura = get_object_or_404(FaturaAGT, **lookup)

        if not fatura.agt_id:
            return JsonResponse({'ok': False, 'erro': 'Fatura ainda não submetida à AGT (sem agt_id).'})

        if fatura.agt_status in ('Validada', 'Rejeitada'):
            # Já em estado terminal — não precisa de polling
            return JsonResponse({'ok': True, 'status': fatura.agt_status, 'terminal': True})

        try:
            data = _consultar_status_agt(fatura.agt_id)
            novo_status = data.get('status', fatura.agt_status)
            if novo_status in dict(FaturaAGT.STATUS_AGT):
                fatura.agt_status = novo_status
            fatura.agt_resposta_raw = data
            fatura.agt_hash = data.get('hash', fatura.agt_hash) or fatura.agt_hash
            fatura.agt_qr_code = data.get('qrCode', '') or data.get('qr_code', fatura.agt_qr_code) or fatura.agt_qr_code
            if novo_status == 'Validada' and not fatura.agt_data_validacao:
                fatura.agt_data_validacao = timezone.now()
            if novo_status == 'Rejeitada':
                fatura.agt_motivo_rejeicao = data.get('motivoRejeicao', '') or data.get('motivo_rejeicao', '') or fatura.agt_motivo_rejeicao
            fatura.save()
        except Exception as exc:
            logger.warning('Erro ao consultar AGT para fatura pk=%s: %s', fatura.pk, exc)
            # Mesmo com erro de rede, devolve o status actual
            return JsonResponse({'ok': True, 'status': fatura.agt_status, 'aviso': str(exc)})

        return JsonResponse({'ok': True, 'status': fatura.agt_status})

    except Exception as exc:
        logger.error('Erro inesperado em faturacao_agt_sincronizar pk=%s: %s', pk, exc)
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=500)


@csrf_exempt
def faturacao_agt_callback(request):
    """
    Webhook AGT — recebe notificações de status de processamento.
    URL pública: https://sicdoa.cdoangola.co.ao/api/facturacaoelectronica/callback

    Nota: a documentação AGT indica que callbacks estarão disponíveis
    em versões futuras. Este endpoint já está activo e pronto a receber.

    Segurança:
        Definir AGT_CALLBACK_SECRET no settings/.env.
        A AGT enviará o valor no header X-AGT-Secret.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'detail': 'Method not allowed'}, status=405)

    # Verificação de segredo partilhado
    secret = getattr(settings, 'AGT_CALLBACK_SECRET', None)
    if secret:
        received_token = request.headers.get('X-AGT-Secret', '')
        if received_token != secret:
            logger.warning(
                'Callback AGT rejeitado: token inválido. IP=%s',
                request.META.get('REMOTE_ADDR', 'desconhecido'),
            )
            return JsonResponse({'status': 'error', 'detail': 'Unauthorized'}, status=401)
    else:
        logger.warning(
            'AGT_CALLBACK_SECRET não configurado — callback aceite sem autenticação. '
            'Definir settings.AGT_CALLBACK_SECRET para activar verificação.'
        )

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'detail': 'JSON inválido'}, status=400)

    try:
        # Suportar tanto 'agt_id' como 'requestID' como 'fatura_id'
        agt_id = (
            payload.get('agt_id')
            or payload.get('requestID')
            or payload.get('fatura_id', '')
        )
        novo_status = payload.get('status', '')
        motivo = payload.get('motivoRejeicao') or payload.get('motivo_rejeicao', '')
        agt_hash = payload.get('hash', '')
        qr_code = payload.get('qrCode') or payload.get('qr_code', '')

        if not agt_id:
            return JsonResponse({'status': 'error', 'detail': 'agt_id em falta no payload'}, status=400)

        fatura = FaturaAGT.objects.filter(agt_id=agt_id).first()
        if fatura is None:
            logger.warning('Callback AGT: fatura com agt_id=%s não encontrada.', agt_id)
            return JsonResponse({'status': 'error', 'detail': 'Fatura não encontrada'}, status=404)

        if novo_status and novo_status in dict(FaturaAGT.STATUS_AGT):
            fatura.agt_status = novo_status
        if motivo:
            fatura.agt_motivo_rejeicao = motivo
        if agt_hash:
            fatura.agt_hash = agt_hash
        if qr_code:
            fatura.agt_qr_code = qr_code
        if novo_status == 'Validada' and not fatura.agt_data_validacao:
            fatura.agt_data_validacao = timezone.now()
        fatura.agt_resposta_raw = payload
        fatura.save()

        logger.info('Callback AGT processado: fatura pk=%s → status=%s', fatura.pk, fatura.agt_status)
        return JsonResponse({'status': 'ok'})

    except Exception as exc:
        logger.error('Erro no callback AGT: %s', exc, exc_info=True)
        return JsonResponse({'status': 'error', 'detail': str(exc)}, status=400)
