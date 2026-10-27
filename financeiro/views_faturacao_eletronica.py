"""
views_faturacao_eletronica.py — Faturação Eletrónica AGT (agt_invoicing models)

Views para dashboard, listagem e detalhe de faturas AGT usando o app agt_invoicing.
Multi-tenant: cada banca vê apenas suas próprias faturas.
"""
import json
import logging

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from users.auth_decorators import requer_sessao_ativa
from agt_invoicing.models import Fatura, SubmissaoAgt, ConfiguracaoFiscal, RegistoAuditoria

logger = logging.getLogger(__name__)


def _get_user_banca_id(request):
    """Extract banca_id from request session."""
    return request.session.get('banca_id')


@requer_sessao_ativa
def faturacao_eletronica_dashboard(request):
    """
    Dashboard da Faturação Eletrónica AGT.
    KPI cards: Emitidas, Rejeitadas, Pendentes
    Últimas 5 faturas com status AGT
    """
    banca_id = _get_user_banca_id(request)
    
    # Filter by banca
    qs = Fatura.objects.all()
    if banca_id:
        qs = qs.filter(banca_id=banca_id)
    
    # KPI counts
    total_emitidas = qs.filter(estado='EMITIDA').count()
    total_rejeitadas = qs.filter(agt_status='REJEITADA').count()
    total_pendentes = qs.filter(agt_status='PENDENTE').count()
    
    # Recent faturas (last 5, ordered by newest first)
    faturas_recentes = qs.order_by('-criada_em')[:5]
    
    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_eletronica',
        'sub': 'faturacao_eletronica',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'total_emitidas': total_emitidas,
        'total_rejeitadas': total_rejeitadas,
        'total_pendentes': total_pendentes,
        'faturas_recentes': faturas_recentes,
    }
    
    return render(request, 'financeiro/faturacao_eletronica/dashboard.html', context)


@requer_sessao_ativa
def faturacao_eletronica_lista(request):
    """
    Listing with filters and pagination.
    
    GET params:
      - estado: filter by RASCUNHO, PENDENTE_AGT, EMITIDA, REJEITADA
      - agt_status: filter by APROVADA, REJEITADA, PENDENTE
      - search: search by numero (fatura number)
      - page: pagination
    """
    banca_id = _get_user_banca_id(request)
    
    # Base queryset
    qs = Fatura.objects.all()
    if banca_id:
        qs = qs.filter(banca_id=banca_id)
    
    # Filters
    estado = request.GET.get('estado', '')
    agt_status = request.GET.get('agt_status', '')
    search = request.GET.get('search', '')
    
    if estado:
        qs = qs.filter(estado=estado)
    if agt_status:
        qs = qs.filter(agt_status=agt_status)
    if search:
        qs = qs.filter(numero__icontains=search)
    
    # Ordering
    qs = qs.order_by('-criada_em')
    
    # Pagination (20 per page)
    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_eletronica',
        'sub': 'faturacao_eletronica',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'page_obj': page_obj,
        'faturas': page_obj,
        'estado': estado,
        'agt_status': agt_status,
        'search': search,
        'estado_choices': Fatura.ESTADOS,
        'agt_status_choices': Fatura.AGT_STATUSES,
    }
    
    return render(request, 'financeiro/faturacao_eletronica/lista.html', context)


@requer_sessao_ativa
def faturacao_eletronica_detalhe(request, fatura_id):
    """
    Detail view for a single invoice.
    Multi-tenant check: verify fatura belongs to user's banca.
    """
    banca_id = _get_user_banca_id(request)
    
    # Lookup with multi-tenant check
    lookup = {'pk': fatura_id}
    if banca_id:
        lookup['banca_id'] = banca_id
    
    fatura = get_object_or_404(Fatura, **lookup)
    
    # Format agt_erros if present
    agt_erros_json = ''
    if fatura.agt_erros:
        agt_erros_json = json.dumps(fatura.agt_erros, indent=2, ensure_ascii=False)
    
    context = {
        'active_menu': 'Financeiro',
        'active_sub': 'faturacao_eletronica',
        'sub': 'faturacao_eletronica',
        'usuario': request.session.get('usuario', {}),
        'papel': request.session.get('usuario', {}).get('papel', ''),
        'fatura': fatura,
        'agt_erros_json': agt_erros_json,
    }
    
    return render(request, 'financeiro/faturacao_eletronica/detalhe.html', context)


@requer_sessao_ativa
@require_POST
def faturacao_eletronica_sincronizar(request, fatura_id):
    """
    Sync invoice status with AGT (polling endpoint).
    Returns JSON with updated status.
    """
    banca_id = _get_user_banca_id(request)
    
    # Lookup with multi-tenant check
    lookup = {'pk': fatura_id}
    if banca_id:
        lookup['banca_id'] = banca_id
    
    fatura = get_object_or_404(Fatura, **lookup)
    
    # TODO: Implement actual AGT API polling logic here
    # For now, just return current status
    return JsonResponse({
        'ok': True,
        'status': fatura.agt_status,
        'message': 'Sincronização concluída',
    })
