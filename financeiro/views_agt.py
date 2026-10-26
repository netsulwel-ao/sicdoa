"""
Faturação Eletrónica AGT — views
Gestão e acompanhamento de faturas validadas pela AGT (Administração Geral Tributária)
"""
import json
import logging
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from users.auth_decorators import requer_sessao_ativa
from .views import requer_escrita_financeira
from .models import FaturaAGT, FacturaCliente

logger = logging.getLogger(__name__)

CALLBACK_URL = "https://bejames.online/api/facturacaoelectronica/callback"
AGT_API_BASE = "https://efatura.hml.minfin.gov.ao/api/v1"


@requer_sessao_ativa
def faturacao_agt_dashboard(request):
    """Dashboard principal da Faturação Eletrónica AGT."""
    banca_id = request.session.get('banca_id')
    qs = FaturaAGT.objects.all()
    if banca_id:
        qs = qs.filter(banca_id=banca_id)

    total_pendentes = qs.filter(agt_status='Pendente').count()
    total_emitidas = qs.filter(agt_status='Validada').count()
    total_rejeitadas = qs.filter(agt_status='Rejeitada').count()
    total_validadas = total_emitidas

    faturas_recentes = qs.select_related('factura').order_by('-data_emissao')[:5]

    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_agt',
        'sub': 'faturacao_agt',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'total_pendentes': total_pendentes,
        'total_emitidas': total_emitidas,
        'total_rejeitadas': total_rejeitadas,
        'total_validadas': total_validadas,
        'faturas_recentes': faturas_recentes,
        'callback_url': CALLBACK_URL,
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
            Q(numero_fatura__icontains=busca) | Q(nome_cliente__icontains=busca)
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
    """Detalhe de uma fatura AGT."""
    fatura = get_object_or_404(FaturaAGT, pk=pk)
    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_agt',
        'sub': 'faturacao_agt',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'fatura': fatura,
    }
    return render(request, 'financeiro/faturacao_agt_detalhe.html', context)


# Finding 3 fix: correct decorator order — session check first, then method guard, then write perm.
@requer_sessao_ativa
@require_POST
@requer_escrita_financeira
def faturacao_agt_submeter(request, factura_pk):
    """Submete uma FacturaCliente para validação na AGT."""
    factura = get_object_or_404(FacturaCliente, pk=factura_pk)
    usuario = request.session.get('usuario', {})

    fatura, created = FaturaAGT.objects.get_or_create(
        factura=factura,
        defaults={
            'banca_id': request.session.get('banca_id'),
            'nif_cliente': getattr(factura.cliente, 'nif', '') if hasattr(factura, 'cliente') and factura.cliente else '',
            'nome_cliente': getattr(factura.cliente, 'nome', '') if hasattr(factura, 'cliente') and factura.cliente else '',
            'valor_total': getattr(factura, 'valor_total', 0),
            'criado_por_id': request.session.get('usuario_id'),
            'criado_por_nome': usuario.get('nome', ''),
        }
    )

    if not created:
        # Actualizar campos existentes
        if hasattr(factura, 'cliente') and factura.cliente:
            fatura.nif_cliente = getattr(factura.cliente, 'nif', '') or fatura.nif_cliente
            fatura.nome_cliente = getattr(factura.cliente, 'nome', '') or fatura.nome_cliente
        fatura.valor_total = getattr(factura, 'valor_total', fatura.valor_total)

    fatura.agt_status = 'Processando'
    fatura.save()

    # Tentar chamada à API AGT
    try:
        import requests  # noqa: PLC0415
        payload = {
            'numero_fatura': fatura.numero_fatura,
            'nif_emitente': fatura.nif_emitente,
            'nif_cliente': fatura.nif_cliente,
            'nome_cliente': fatura.nome_cliente,
            'valor_total': str(fatura.valor_total),
            'taxa_iva': str(fatura.taxa_iva),
            'callback_url': CALLBACK_URL,
        }
        response = requests.post(
            f"{AGT_API_BASE}/faturas",
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        fatura.agt_id = data.get('id', '')
        fatura.agt_hash = data.get('hash', '')
        fatura.agt_resposta_raw = data
        fatura.save()
    except Exception as exc:  # requests.RequestException or any other error
        logger.warning("Erro ao submeter fatura AGT pk=%s: %s", fatura.pk, exc)
        fatura.agt_status = 'Erro'
        fatura.agt_motivo_rejeicao = str(exc)
        fatura.save()

    return redirect(reverse('financeiro:faturacao_agt_detalhe', args=[fatura.pk]))


# Finding 1 fix: convert to POST-only to prevent GET-based state mutation.
# Templates use JavaScript fetch with CSRF token instead of plain <a href>.
@requer_sessao_ativa
@require_POST
def faturacao_agt_sincronizar(request, pk):
    """
    Consulta o status actualizado da fatura na AGT.
    Aceita apenas POST para prevenir mutação de estado via GET
    (browser prefetch, histórico de navegação, etc.).
    """
    try:
        fatura = get_object_or_404(FaturaAGT, pk=pk)

        if fatura.agt_id and fatura.agt_status == 'Processando':
            try:
                import requests  # noqa: PLC0415
                response = requests.get(
                    f"{AGT_API_BASE}/faturas/{fatura.agt_id}",
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                novo_status = data.get('status', fatura.agt_status)
                if novo_status in dict(FaturaAGT.STATUS_AGT):
                    fatura.agt_status = novo_status
                fatura.agt_resposta_raw = data
                if novo_status == 'Validada':
                    fatura.agt_data_validacao = timezone.now()
                fatura.save()
            except Exception as exc:
                logger.warning("Erro ao sincronizar fatura AGT pk=%s: %s", fatura.pk, exc)

        return JsonResponse({'status': fatura.agt_status, 'ok': True})
    except Exception as exc:
        return JsonResponse({'ok': False, 'erro': str(exc)}, status=500)


@csrf_exempt
def faturacao_agt_callback(request):
    """
    Webhook AGT — recebe notificações de status de processamento de faturas.
    URL pública: https://bejames.online/api/facturacaoelectronica/callback

    Finding 2 fix: verifica token secreto configurado em settings.AGT_CALLBACK_SECRET.
    Se a setting não estiver definida, regista aviso e aceita (modo degradado).
    Para activar a verificação, adicionar ao settings.py:
        AGT_CALLBACK_SECRET = "um-segredo-forte-partilhado-com-a-agt"
    e configurar o mesmo valor no portal AGT para que seja enviado no header
    X-AGT-Secret de cada callback.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'detail': 'Method not allowed'}, status=405)

    # Verificação de segredo partilhado (Finding 2)
    secret = getattr(settings, 'AGT_CALLBACK_SECRET', None)
    if secret:
        received_token = request.headers.get('X-AGT-Secret', '')
        if received_token != secret:
            logger.warning(
                "Callback AGT rejeitado: token inválido. IP=%s",
                request.META.get('REMOTE_ADDR', 'desconhecido'),
            )
            return JsonResponse({'status': 'error', 'detail': 'Unauthorized'}, status=401)
    else:
        logger.warning(
            "AGT_CALLBACK_SECRET não configurado — callback aceite sem autenticação. "
            "Defina settings.AGT_CALLBACK_SECRET para activar a verificação."
        )

    try:
        payload = json.loads(request.body)
        agt_id = payload.get('agt_id') or payload.get('fatura_id', '')
        novo_status = payload.get('status', '')
        motivo = payload.get('motivo_rejeicao', '')
        agt_hash = payload.get('hash', '')
        qr_code = payload.get('qr_code', '')

        fatura = FaturaAGT.objects.filter(agt_id=agt_id).first()
        if fatura is None:
            return JsonResponse({'status': 'error', 'detail': 'Fatura não encontrada'}, status=404)

        if novo_status in dict(FaturaAGT.STATUS_AGT):
            fatura.agt_status = novo_status
        if motivo:
            fatura.agt_motivo_rejeicao = motivo
        if agt_hash:
            fatura.agt_hash = agt_hash
        if qr_code:
            fatura.agt_qr_code = qr_code
        if novo_status == 'Validada':
            fatura.agt_data_validacao = timezone.now()
        fatura.agt_resposta_raw = payload
        fatura.save()

        return JsonResponse({'status': 'ok'})
    except Exception as exc:
        logger.error("Erro no callback AGT: %s", exc)
        return JsonResponse({'status': 'error', 'detail': str(exc)}, status=400)
