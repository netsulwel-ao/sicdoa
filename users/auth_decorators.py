"""
Decoradores customizados para autenticação com sessão expirável de 1 hora.
"""
from django.shortcuts import redirect
from django.utils import timezone
from datetime import timedelta


def sessao_expirada(request):
    """
    Verifica se a sessão do usuário expirou (1 hora).
    Retorna True se expirou, False caso contrário.
    """
    if not request.session.get('usuario_id'):
        return True
    
    # Verificar timestamp da sessão
    login_time = request.session.get('login_time')
    if not login_time:
        return True
    
    # Converter string para datetime se necessário
    if isinstance(login_time, str):
        try:
            from datetime import datetime
            login_time = datetime.fromisoformat(login_time)
        except (ValueError, TypeError):
            return True
    
    agora = timezone.now()
    if agora - login_time > timedelta(hours=1):
        return True
    
    return False


def requer_sessao_ativa(view_func):
    """
    Decorador que requer sessão ativa e não expirada.
    Se a sessão expirou, limpa a sessão e redireciona para login.
    """
    def wrapper(request, *args, **kwargs):
        # Verificar se há sessão
        if not request.session.get('usuario_id'):
            return redirect('login')
        
        if sessao_expirada(request):
            request.session.flush()
            return redirect('login')
        
        request.session['login_time'] = timezone.now().isoformat()
        request.session.modified = True
        
        return view_func(request, *args, **kwargs)
    
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


def tempo_restante_sessao(request):
    """
    Retorna o tempo restante da sessão em minutos.
    Se não houver sessão ou estiver expirada, retorna 0.
    """
    if not request.session.get('login_time'):
        return 0
    
    try:
        from datetime import datetime
        login_time_str = request.session['login_time']
        if isinstance(login_time_str, str):
            login_time = datetime.fromisoformat(login_time_str)
        else:
            login_time = login_time_str
        
        agora = timezone.now()
        tempo_decorrido = agora - login_time
        tempo_total = timedelta(hours=1)
        tempo_restante = tempo_total - tempo_decorrido
        
        # Retornar minutos restantes (mínimo 0)
        return max(0, int(tempo_restante.total_seconds() / 60))
    except (ValueError, TypeError, KeyError):
        return 0


def criar_sessao_usuario(request, usuario):
    """
    Cria uma nova sessão para o usuário com timestamp de expiração.
    """
    # Limpar sessão anterior
    request.session.flush()
    
    # Guardar informações do utilizador na sessão
    request.session['usuario_id'] = usuario.id
    funcao_nome = usuario.funcao.nome if hasattr(usuario, 'funcao') and usuario.funcao else ''
    # Se não for Administrador nem Despachante Oficial, o papel passa a ser o nome da função
    if usuario.papel not in ('Administrador', 'Despachante Oficial') and funcao_nome:
        papel_sessao = funcao_nome
    else:
        papel_sessao = usuario.papel
    request.session['usuario'] = {
        'id': usuario.id,
        'nome': usuario.nome,
        'email': usuario.email,
        'papel': papel_sessao,
        'nif': usuario.nif or '',
        'cedula': usuario.cedula or '',
        'telefone': usuario.telefone or '',
        'username': usuario.username,
        'is_secretario': usuario.is_secretario,
        'is_vice_secretario': usuario.is_vice_secretario,
        'funcao_nome': funcao_nome,
    }
    
    # Guardar tipo de usuário (usuario ou colaborador)
    if hasattr(usuario, 'tipo'):
        request.session['tipo_usuario'] = usuario.tipo
        if usuario.tipo == 'colaborador' and hasattr(usuario, 'colaborador_id'):
            request.session['colaborador_id'] = usuario.colaborador_id
    else:
        request.session['tipo_usuario'] = 'usuario'
    
    # Guardar timestamp de login
    request.session['login_time'] = timezone.now().isoformat()
    
    request.session.set_expiry(3600)
    
    return request.session


def limpar_sessao(request):
    """
    Limpa completamente a sessão do usuário.
    """
    request.session.flush()
    return request.session
