"""
Decoradores customizados para autenticação com sessão expirável de 1 hora.
"""
from django.shortcuts import redirect
from django.utils import timezone


def sessao_expirada(request):
    """
    Verifica se a sessão do usuário expirou (1 hora).
    Retorna True se expirou, False caso contrário.
    """
    if not request.session.get('usuario_id'):
        return True

    login_time = request.session.get('login_time')
    if not isinstance(login_time, (int, float)):
        return True

    return (timezone.now().timestamp() - login_time) > 3600


def requer_sessao_ativa(view_func):
    """
    Decorador que requer sessão ativa e não expirada.
    Se a sessão expirou, limpa a sessão e redireciona para login.
    """
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')

        if sessao_expirada(request):
            request.session.flush()
            return redirect('login')

        request.session['login_time'] = timezone.now().timestamp()
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
    login_time = request.session.get('login_time')
    if not isinstance(login_time, (int, float)):
        return 0

    restante = 3600 - (timezone.now().timestamp() - login_time)
    return max(0, int(restante / 60))


def tempo_restante_segundos(request):
    """
    Retorna o tempo restante da sessão em segundos.
    Usado pelas APIs de status para contagem regressiva precisa.
    """
    login_time = request.session.get('login_time')
    if not isinstance(login_time, (int, float)):
        return 0

    restante = 3600 - (timezone.now().timestamp() - login_time)
    return max(0, int(restante))


def criar_sessao_usuario(request, usuario):
    """
    Cria uma nova sessão para o usuário com timestamp de expiração.
    """
    request.session.flush()

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
        'foto': getattr(usuario, 'foto', '') or '',
        'is_secretario': getattr(usuario, 'is_secretario', False),
        'is_vice_secretario': getattr(usuario, 'is_vice_secretario', False),
        'funcao_nome': funcao_nome,
        'cargo_banca_nome': cargo_banca_nome,
        'permissoes': permissoes_lista,
    }

    if hasattr(usuario, 'tipo'):
        request.session['tipo_usuario'] = usuario.tipo
        if usuario.tipo == 'colaborador' and hasattr(usuario, 'colaborador_id'):
            request.session['colaborador_id'] = usuario.colaborador_id
        if usuario.tipo == 'colaborador' and hasattr(usuario, 'banca_usuario_id'):
            request.session['banca_usuario_id'] = usuario.banca_usuario_id
            if hasattr(usuario, 'banca_id'):
                request.session['banca_id'] = usuario.banca_id
            if hasattr(usuario, 'colaborador_id'):
                from rh.models import Colaborador
                col_filial = Colaborador.objects.filter(pk=usuario.colaborador_id).values_list('filial_id', flat=True).first()
                if col_filial:
                    request.session['colaborador_filial_id'] = col_filial
    else:
        request.session['tipo_usuario'] = 'usuario'
        if usuario.papel != 'Administrador':
            request.session['banca_usuario_id'] = usuario.id
            from rh.models import Banca
            banca = Banca.objects.filter(usuario_id=usuario.id).first()
            if banca:
                request.session['banca_id'] = banca.id
            if not request.session.get('banca_id'):
                from rh.models import Colaborador as _Col
                col = _Col.objects.select_related('banca', 'filial').filter(usuario_id=usuario.id).first()
                if col and col.banca_id:
                    request.session['banca_id'] = col.banca_id
                    if col.filial_id:
                        request.session['colaborador_filial_id'] = col.filial_id

    request.session['login_time'] = timezone.now().timestamp()

    request.session.set_expiry(3600)

    return request.session


def limpar_sessao(request):
    """
    Limpa completamente a sessão do usuário.
    """
    request.session.flush()
    return request.session
