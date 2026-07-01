from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse
from users.auth_decorators import requer_sessao_ativa, tempo_restante_sessao
from rh.models import Colaborador


@login_required
def dashboard_colaborador_view(request):
    """Dashboard principal para colaboradores."""
    # Verificar se a sessão está ativa
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    # Verificar se a sessão expirou
    if request.session.get('login_time'):
        login_time = timezone.datetime.fromisoformat(request.session['login_time'])
        tempo_decorrido = (timezone.now() - login_time).total_seconds() / 60
        if tempo_decorrido > 60:  # 1 hora
            return redirect('login')
    
    # Verificar se é um colaborador
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    # Buscar informações do colaborador
    colaborador_id = request.session.get('colaborador_id')
    if not colaborador_id:
        return redirect('login')
    
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    # Adicionar tempo restante da sessão ao contexto
    tempo_restante = tempo_restante_sessao(request)
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Dashboard',
        'tempo_restante_sessao': tempo_restante,
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    if colaborador.e_gestor_filial:
        # Dashboard para responsável de filial
        return render(request, 'colaboradores/responsavel_dashboard.html', contexto)
    else:
        # Dashboard para colaborador comum
        return render(request, 'colaboradores/dashboard.html', contexto)


@login_required
def perfil_view(request):
    """Página de perfil do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Meus Dados',
        'active_sub': 'perfil',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/perfil.html', contexto)


@login_required
def documentos_view(request):
    """Página de documentos do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Meus Dados',
        'active_sub': 'documentos',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/documentos.html', contexto)


@login_required
def presenca_view(request):
    """Página de controlo de presença do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Presença',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/presenca.html', contexto)


@login_required
def salario_view(request):
    """Página de informações salariais do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Salarial',
        'active_sub': 'salario',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/salario.html', contexto)


@login_required
def historico_salarial_view(request):
    """Página de histórico salarial do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Salarial',
        'active_sub': 'historico-salarial',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/historico_salarial.html', contexto)


@login_required
def ferias_view(request):
    """Página de solicitação de férias do colaborador."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Ferias',
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/ferias.html', contexto)


@login_required
def buscar_view(request):
    """Página de resultados de busca para colaboradores."""
    if not request.session.get('usuario_id'):
        return redirect('login')
    
    if request.session.get('tipo_usuario') != 'colaborador':
        return redirect('login')
    
    query = request.GET.get('q', '').strip()
    if not query:
        return redirect('dashboard_colaborador')
    
    colaborador_id = request.session.get('colaborador_id')
    try:
        colaborador = Colaborador.objects.select_related('cargo_banca').get(id=colaborador_id)
    except Colaborador.DoesNotExist:
        return redirect('login')
    
    contexto = {
        'nome': colaborador.nome,
        'papel': colaborador.cargo_banca.nome if colaborador.cargo_banca_id else 'Colaborador',
        'active_menu': 'Dashboard',
        'query': query,
        'colaborador': colaborador,
        'e_responsavel': colaborador.e_gestor_filial,
    }
    
    return render(request, 'colaboradores/buscar.html', contexto)
