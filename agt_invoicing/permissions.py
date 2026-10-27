"""
Permission decorators for AGT Invoicing endpoints.
"""
from functools import wraps
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)


def require_financial_permission():
    """
    Decorator to check financial permissions.
    Validates:
    - request.session['usuario']['papel'] in whitelist ['Administrador', 'Despachante Oficial']
    - request.session.get('banca_id') exists
    
    Returns 403 Forbidden if validation fails.
    Adds banca_id to view kwargs for multi-tenant filtering.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Check if usuario is in session
            usuario = request.session.get('usuario')
            if not usuario:
                logger.warning(f"User not authenticated in session")
                return JsonResponse(
                    {"error": "Unauthorized", "detail": "User not in session"},
                    status=403
                )

            # Check papel (role)
            papel = usuario.get('papel')
            whitelist = ['Administrador', 'Despachante Oficial']
            
            if papel not in whitelist:
                logger.warning(f"User {usuario.get('id')} has papel '{papel}' (not in whitelist)")
                return JsonResponse(
                    {"error": "Forbidden", "detail": f"Role '{papel}' not authorized"},
                    status=403
                )

            # Check banca_id (multi-tenant)
            banca_id = request.session.get('banca_id')
            if not banca_id:
                logger.warning(f"User {usuario.get('id')} missing banca_id in session")
                return JsonResponse(
                    {"error": "Forbidden", "detail": "banca_id missing"},
                    status=403
                )

            # Add banca_id to kwargs for view to use in multi-tenant filtering
            kwargs['banca_id'] = banca_id

            return view_func(request, *args, **kwargs)

        return wrapper
    return decorator
