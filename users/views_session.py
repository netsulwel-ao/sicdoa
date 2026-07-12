"""
Views adicionais para gestão de sessão
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .auth_decorators import criar_sessao_usuario, tempo_restante_sessao, tempo_restante_segundos


@require_http_methods(['POST'])
def extend_session_view(request):
    """
    View para estender a sessão do usuário por mais 1 hora.
    Retorna JSON com o novo tempo restante.
    """
    if not request.session.get('usuario_id'):
        return JsonResponse({'success': False, 'error': 'Sessão inválida'}, status=401)
    
    try:
        # Estender sessão atualizando o timestamp
        request.session['login_time'] = timezone.now().timestamp()
        request.session.modified = True
        
        request.session.set_expiry(3600)
        
        # Retornar novo tempo restante
        tempo_restante = tempo_restante_segundos(request)
        
        return JsonResponse({
            'success': True,
            'tempo_restante': tempo_restante,
            'message': 'Sessão renovada com sucesso'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def session_status_view(request):
    """
    View para verificar o status da sessão atual.
    Retorna JSON com informações da sessão.
    """
    if not request.session.get('usuario_id'):
        return JsonResponse({
            'active': False,
            'tempo_restante': 0
        })
    
    tempo_restante = tempo_restante_segundos(request)
    
    return JsonResponse({
        'active': True,
        'tempo_restante': tempo_restante,
        'usuario_id': request.session.get('usuario_id'),
        'usuario_nome': request.session.get('usuario', {}).get('nome', '')
    })
