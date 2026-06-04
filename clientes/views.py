from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Cliente
from utils.validators import email_ja_existe


def _requer_sessao(fn):
    """Decorator para verificar se o usuário está autenticado"""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('usuario_id'):
            return redirect('login')
        return fn(request, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


def _ctx(request, sub='', extra=None):
    """Contexto base para templates"""
    u = request.session['usuario']
    ctx = {'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
           'active_menu': 'Clientes', 'active_sub': sub}
    if extra:
        ctx.update(extra)
    return ctx


@_requer_sessao
def lista_clientes(request):
    """View para listar todos os clientes"""
    busca = request.GET.get('busca', '')
    usuario_id = request.session.get('usuario_id')
    clientes_query = Cliente.objects.filter(ativo=True)
    
    # Filtrar clientes por usuário logado
    if usuario_id:
        clientes_query = clientes_query.filter(usuario_id=usuario_id)
    
    if busca:
        clientes_query = clientes_query.filter(
            Q(nome__icontains=busca) |
            Q(nif__icontains=busca) |
            Q(localizacao__icontains=busca)
        )
    
    paginator = Paginator(clientes_query, 8)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = _ctx(request, 'lista', {
        'page_obj': page_obj,
        'busca': busca,
        'total_clientes': clientes_query.count()
    })
    
    return render(request, 'clientes/lista.html', context)


@_requer_sessao
def criar_cliente(request):
    """View para criar um novo cliente"""
    if request.method == 'POST':
        try:
            nome = request.POST.get('nome', '').strip()
            nif = request.POST.get('nif', '').strip()
            localizacao = request.POST.get('localizacao', '').strip()
            telefone = request.POST.get('telefone', '').strip()
            email = request.POST.get('email', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()
            
            if not nome or not nif or not localizacao:
                messages.error(request, 'Os campos Nome, NIF e Localização são obrigatórios.')
                context = _ctx(request, 'criar', {
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            # Verificar se NIF já existe
            if Cliente.objects.filter(nif=nif).exists():
                messages.error(request, 'Já existe um cliente cadastrado com este NIF.')
                context = _ctx(request, 'criar', {
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)

            # Verificar se email já existe no sistema
            if email and email_ja_existe(email):
                messages.error(request, 'Este email já está registado no sistema.')
                context = _ctx(request, 'criar', {
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            cliente = Cliente.objects.create(
                nome=nome,
                nif=nif,
                localizacao=localizacao,
                telefone=telefone,
                email=email,
                observacoes=observacoes,
                usuario_id=request.session.get('usuario_id')
            )
            
            messages.success(request, f'Cliente "{cliente.nome}" cadastrado com sucesso!')
            return redirect('clientes:lista')
            
        except Exception as e:
            messages.error(request, f'Erro ao cadastrar cliente: {str(e)}')
            context = _ctx(request, 'criar', {
                'form_data': request.POST
            })
            return render(request, 'clientes/form.html', context)
    
    context = _ctx(request, 'criar')
    return render(request, 'clientes/form.html', context)


@_requer_sessao
def editar_cliente(request, pk):
    """View para editar um cliente existente"""
    cliente = get_object_or_404(Cliente, pk=pk, ativo=True)
    
    if request.method == 'POST':
        try:
            nome = request.POST.get('nome', '').strip()
            nif = request.POST.get('nif', '').strip()
            localizacao = request.POST.get('localizacao', '').strip()
            telefone = request.POST.get('telefone', '').strip()
            email = request.POST.get('email', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()
            
            if not nome or not nif or not localizacao:
                messages.error(request, 'Os campos Nome, NIF e Localização são obrigatórios.')
                context = _ctx(request, 'editar', {
                    'cliente': cliente,
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            # Verificar se NIF já existe (exceto para este cliente)
            if Cliente.objects.filter(nif=nif).exclude(pk=pk).exists():
                messages.error(request, 'Já existe um cliente cadastrado com este NIF.')
                context = _ctx(request, 'editar', {
                    'cliente': cliente,
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)

            # Verificar se email já existe no sistema (exceto para este cliente)
            if email and email_ja_existe(email, exclude_model=Cliente, exclude_pk=pk):
                messages.error(request, 'Este email já está registado no sistema.')
                context = _ctx(request, 'editar', {
                    'cliente': cliente,
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            cliente.nome = nome
            cliente.nif = nif
            cliente.localizacao = localizacao
            cliente.telefone = telefone
            cliente.email = email
            cliente.observacoes = observacoes
            cliente.usuario_id = request.session.get('usuario_id')
            cliente.save()
            
            messages.success(request, f'Cliente "{cliente.nome}" atualizado com sucesso!')
            return redirect('clientes:lista')
            
        except Exception as e:
            messages.error(request, f'Erro ao atualizar cliente: {str(e)}')
            context = _ctx(request, 'editar', {
                'cliente': cliente,
                'form_data': request.POST
            })
            return render(request, 'clientes/form.html', context)
    
    context = _ctx(request, 'editar', {'cliente': cliente})
    return render(request, 'clientes/form.html', context)


@_requer_sessao
def detalhar_cliente(request, pk):
    """View para visualizar detalhes de um cliente"""
    cliente = get_object_or_404(Cliente, pk=pk, ativo=True)
    
    context = _ctx(request, 'detalhes', {'cliente': cliente})
    return render(request, 'clientes/detalhes.html', context)


@_requer_sessao
def excluir_cliente(request, pk):
    """View para excluir permanentemente um cliente"""
    cliente = get_object_or_404(Cliente, pk=pk)
    
    if request.method == 'POST':
        try:
            nome_cliente = cliente.nome
            cliente.delete()
            messages.success(request, f'Cliente "{nome_cliente}" excluído permanentemente da base de dados!')
            return redirect('clientes:lista')
        except Exception as e:
            messages.error(request, f'Erro ao excluir cliente: {str(e)}')
            return redirect('clientes:detalhes', pk=pk)
    
    context = _ctx(request, 'excluir', {'cliente': cliente})
    return render(request, 'clientes/confirmar_exclusao.html', context)
