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
            # Se for naive, fazer aware com UTC
            if login_time.tzinfo is None:
                login_time = timezone.make_aware(login_time, timezone.utc)
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
            # Se for naive, fazer aware com UTC
            if login_time.tzinfo is None:
                login_time = timezone.make_aware(login_time, timezone.utc)
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
    papel_sessao = usuario.papel
    cargo_banca_nome = getattr(usuario, 'cargo_banca_nome', '')
    papel_display = getattr(usuario, 'papel_display', '') or funcao_nome or usuario.papel
    permissoes_lista = getattr(usuario, '_permissoes', [])
    request.session['usuario'] = {
        'id': usuario.id,
        'nome': usuario.nome,
        'email': usuario.email,
        'papel': papel_sessao,
        'papel_display': papel_display,
        'nif': usuario.nif or '',
        'cedula': usuario.cedula or '',
        'telefone': usuario.telefone or '',
        'username': usuario.username,
        'is_secretario': getattr(usuario, 'is_secretario', False),
        'is_vice_secretario': getattr(usuario, 'is_vice_secretario', False),
        'funcao_nome': funcao_nome,
        'cargo_banca_nome': cargo_banca_nome,
        'permissoes': permissoes_lista,
    }
    
    # Guardar tipo de usuário (usuario ou colaborador)
    if hasattr(usuario, 'tipo'):
        request.session['tipo_usuario'] = usuario.tipo
        if usuario.tipo == 'colaborador' and hasattr(usuario, 'colaborador_id'):
            request.session['colaborador_id'] = usuario.colaborador_id
        if usuario.tipo == 'colaborador' and hasattr(usuario, 'banca_usuario_id'):
            request.session['banca_usuario_id'] = usuario.banca_usuario_id
            if hasattr(usuario, 'banca_id'):
                request.session['banca_id'] = usuario.banca_id
            # Filial do colaborador
            if hasattr(usuario, 'colaborador_id'):
                from rh.models import Colaborador
                col_filial = Colaborador.objects.filter(pk=usuario.colaborador_id).values_list('filial_id', flat=True).first()
                if col_filial:
                    request.session['colaborador_filial_id'] = col_filial
    else:
        request.session['tipo_usuario'] = 'usuario'
        # Para usuários normais, buscar banca pelo usuario_id
        if usuario.papel != 'Administrador':
            from rh.models import Banca
            banca = Banca.objects.filter(usuario_id=usuario.id).first()
            if banca:
                request.session['banca_id'] = banca.id
    
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
