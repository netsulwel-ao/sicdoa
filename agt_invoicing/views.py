"""
REST API endpoints for AGT Invoicing.

4 Endpoints:
1. GET /api/agt/stats/ — Statistics (emitidas, rejeitadas, pendentes)
2. GET /api/agt/pendentes/ — Paginated list of pending invoices
3. GET /api/agt/estado/<id>/ — Invoice detail
4. POST /api/agt/callback/ — Webhook for AGT callbacks (public, no auth required)
"""
import logging
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import Fatura, RegistoAuditoria
from .permissions import require_financial_permission
from .serializers import FaturaListSerializer, FaturaDetailSerializer, serialize_stats
from .services import FaturaService

logger = logging.getLogger(__name__)


# ─── 1. GET /api/agt/stats/ ────────────────────────────────────────────

@require_financial_permission()
@require_http_methods(["GET"])
def agt_stats(request, banca_id):
    """
    Statistics endpoint.
    Returns counts: emitidas, rejeitadas, pendentes, and groupings by estado and agt_status.
    Multi-tenant: filters by banca_id from session.
    """
    try:
        # Filter faturas by banca_id
        faturas = Fatura.objects.filter(banca_id=banca_id)

        # Count by estado
        por_estado = {}
        for estado, _ in Fatura.ESTADOS:
            count = faturas.filter(estado=estado).count()
            por_estado[estado] = count

        # Count by agt_status
        por_agt_status = {}
        for agt_status, _ in Fatura.AGT_STATUSES:
            count = faturas.filter(agt_status=agt_status).count()
            por_agt_status[agt_status] = count

        # Summary counts
        emitidas = faturas.filter(estado='EMITIDA').count()
        rejeitadas = faturas.filter(agt_status='REJEITADA').count()
        pendentes = faturas.filter(agt_status='PENDENTE').count()

        stats = {
            "emitidas": emitidas,
            "rejeitadas": rejeitadas,
            "pendentes": pendentes,
            "por_estado": por_estado,
            "por_agt_status": por_agt_status,
        }

        return JsonResponse(serialize_stats(stats))

    except Exception as e:
        logger.error(f"Error in agt_stats: {e}", exc_info=True)
        return JsonResponse(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ─── 2. GET /api/agt/pendentes/ ────────────────────────────────────────

@require_financial_permission()
@require_http_methods(["GET"])
def agt_pendentes(request, banca_id):
    """
    Paginated list of pending invoices (agt_status='PENDENTE').
    Pagination: 50 per page.
    Multi-tenant: filters by banca_id.
    """
    try:
        # Filter faturas by banca_id and agt_status
        queryset = Fatura.objects.filter(
            banca_id=banca_id,
            agt_status='PENDENTE'
        ).order_by('-criada_em')

        # Pagination (default limit 50 per page)
        page_num = request.GET.get('page', 1)
        paginator = Paginator(queryset, 50)
        page = paginator.get_page(page_num)

        # Serialize
        serializer = FaturaListSerializer(page, many=True)

        return JsonResponse({
            "count": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page.number,
            "results": serializer.data,
        })

    except Exception as e:
        logger.error(f"Error in agt_pendentes: {e}", exc_info=True)
        return JsonResponse(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ─── 3. GET /api/agt/estado/<id>/ ────────────────────────────────────────

@require_financial_permission()
@require_http_methods(["GET"])
def agt_estado(request, id, banca_id):
    """
    Invoice detail endpoint.
    Returns full Fatura object with all AGT-related fields.
    Multi-tenant: checks banca_id matches session.
    """
    try:
        # Get fatura and verify banca_id matches
        try:
            fatura = Fatura.objects.get(pk=id, banca_id=banca_id)
        except Fatura.DoesNotExist:
            return JsonResponse(
                {"error": "Not found", "detail": f"Fatura {id} not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Serialize
        serializer = FaturaDetailSerializer(fatura)

        return JsonResponse(serializer.data)

    except Exception as e:
        logger.error(f"Error in agt_estado: {e}", exc_info=True)
        return JsonResponse(
            {"error": "Internal server error", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ─── 4. POST /api/agt/callback/ ────────────────────────────────────────

@csrf_exempt
@api_view(['POST'])
def agt_callback(request):
    """
    AGT callback webhook endpoint (public, no authentication required).
    
    CRITICAL: Always return HTTP 200, even on error.
    
    Payload: {requestId, status: 'APPROVED'|'REJECTED'|'PENDING', hash, erros: []}
    
    Logic:
    - Parse payload
    - Call FaturaService.processar_callback()
    - Create RegistoAuditoria with origin_tipo='WEBHOOK'
    - Always return HTTP 200 with {acknowledged: bool, reason: str}
    """
    try:
        # Parse request payload
        if isinstance(request.data, dict):
            payload = request.data
        else:
            payload = {}

        logger.info(f"Callback received: {payload}")

        # Call service to process callback
        service = FaturaService()
        result = service.processar_callback(payload)

        # Create audit log
        try:
            request_id = payload.get("requestId")
            RegistoAuditoria.objects.create(
                banca_id=1,  # FIXME: This should be determined from fatura or config
                acao="UPDATED",
                origin_tipo="WEBHOOK",
                entity_tipo="Callback",
                entity_id=0,
                motivo=f"requestId={request_id}, status={payload.get('status')}",
            )
        except Exception as e:
            logger.warning(f"Failed to create audit log for callback: {e}")

        # ALWAYS return 200, even if callback failed
        acknowledged = result.get("ok", False)
        reason = result.get("reason", "Unknown")

        return Response(
            {
                "acknowledged": acknowledged,
                "reason": reason,
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Unexpected error in agt_callback: {e}", exc_info=True)
        
        # CRITICAL: Still return 200 to acknowledge receipt
        return Response(
            {
                "acknowledged": False,
                "reason": f"Error: {str(e)}",
            },
            status=status.HTTP_200_OK
        )
