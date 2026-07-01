from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from decimal import Decimal
from .models import Cliente
from utils.format_kz import parse_kz
from .acesso import escopo_cliente
from utils.validators import email_ja_existe
from users.permissoes import _is_admin_ou_acesso_total, get_usuario_permissoes


def _usuario_dono(request):
    """Retorna o usuario_id do dono da banca para colaboradores."""
    if request.session.get('tipo_usuario') == 'colaborador':
        from rh.models import Colaborador
        cid = request.session.get('colaborador_id')
        if cid:
            col = Colaborador.objects.select_related('banca').filter(
                pk=cid, estado='Ativo'
            ).first()
            if col and col.banca:
                return col.banca.usuario_id
        return request.session.get('usuario_id')
    return request.session.get('usuario_id')


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
    from rh.acesso import contexto_colaborador
    ctx = {'usuario': u, 'nome': u['nome'], 'papel': u['papel'],
           'active_menu': 'Gestão Aduaneira', 'active_sub': 'clientes'}
    ctx.update(contexto_colaborador(request))
    if extra:
        ctx.update(extra)
    return ctx


def _tem_perm_clientes(request):
    """True se o user tem papel de acesso ou permissão gerir_clientes."""
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel in ('Administrador', 'Despachante Oficial'):
        return True
    if _is_admin_ou_acesso_total(request):
        return True
    permissoes = get_usuario_permissoes(request)
    return 'gerir_clientes' in permissoes or 'gerir_clientes_filial' in permissoes


@_requer_sessao
def lista_clientes(request):
    """View para listar todos os clientes"""
    if not _tem_perm_clientes(request):
        messages.error(request, 'Não tem permissão para aceder aos Clientes.')
        return redirect('dashboard')
    busca = request.GET.get('busca', '')
    clientes_query = escopo_cliente(request, Cliente.objects.filter(ativo=True))
    
    if busca:
        clientes_query = clientes_query.filter(
            Q(nome__icontains=busca) |
            Q(nif__icontains=busca) |
            Q(localizacao__icontains=busca)
        )
    
    clientes_query = clientes_query.order_by('nome')
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
    if not _tem_perm_clientes(request):
        messages.error(request, 'Não tem permissão para criar clientes.')
        return redirect('clientes:lista')
    if request.method == 'POST':
        try:
            nome = request.POST.get('nome', '').strip()
            nif = request.POST.get('nif', '').strip()
            localizacao = request.POST.get('localizacao', '').strip()
            telefone = request.POST.get('telefone', '').strip()
            email = request.POST.get('email', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()
            limite_financeiro = request.POST.get('limite_financeiro', '0').strip()
            
            if not nome or not nif or not localizacao:
                messages.error(request, 'Os campos Nome, NIF e Localização são obrigatórios.')
                context = _ctx(request, 'criar', {
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            try:
                limite_financeiro = Decimal(parse_kz(limite_financeiro) or '0')
            except Exception:
                limite_financeiro = Decimal('0')

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
            
            banca_id = request.session.get('banca_id')
            if not banca_id:
                from rh.models import Banca
                banca_obj = Banca.objects.filter(usuario_id=_usuario_dono(request)).first()
                banca_id = banca_obj.id if banca_obj else None
            filial_id = request.session.get('colaborador_filial_id') if request.session.get('tipo_usuario') == 'colaborador' else None
            cliente = Cliente.objects.create(
                nome=nome,
                nif=nif,
                localizacao=localizacao,
                telefone=telefone,
                email=email,
                observacoes=observacoes,
                limite_financeiro=limite_financeiro,
                usuario_id=_usuario_dono(request),
                banca_id=banca_id,
                filial_id=filial_id,
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
    if not _tem_perm_clientes(request):
        messages.error(request, 'Não tem permissão para editar clientes.')
        return redirect('clientes:lista')
    cliente = get_object_or_404(escopo_cliente(request, Cliente.objects.filter(ativo=True)), pk=pk)
    
    if request.method == 'POST':
        try:
            nome = request.POST.get('nome', '').strip()
            nif = request.POST.get('nif', '').strip()
            localizacao = request.POST.get('localizacao', '').strip()
            telefone = request.POST.get('telefone', '').strip()
            email = request.POST.get('email', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()
            limite_financeiro = request.POST.get('limite_financeiro', '0').strip()
            
            if not nome or not nif or not localizacao:
                messages.error(request, 'Os campos Nome, NIF e Localização são obrigatórios.')
                context = _ctx(request, 'editar', {
                    'cliente': cliente,
                    'form_data': request.POST
                })
                return render(request, 'clientes/form.html', context)
            
            try:
                limite_financeiro = Decimal(parse_kz(limite_financeiro) or '0')
            except Exception:
                limite_financeiro = Decimal('0')

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
            cliente.limite_financeiro = limite_financeiro
            cliente.usuario_id = _usuario_dono(request)
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
    if not _tem_perm_clientes(request):
        messages.error(request, 'Não tem permissão para aceder aos Clientes.')
        return redirect('dashboard')
    cliente = get_object_or_404(escopo_cliente(request, Cliente.objects.filter(ativo=True)), pk=pk)
    
    context = _ctx(request, 'detalhes', {'cliente': cliente})
    return render(request, 'clientes/detalhes.html', context)


@_requer_sessao
def excluir_cliente(request, pk):
    """View para desativar (soft-delete) um cliente"""
    if not _tem_perm_clientes(request):
        messages.error(request, 'Não tem permissão para excluir clientes.')
        return redirect('clientes:lista')
    from clientes.models import Cliente
    cliente = get_object_or_404(escopo_cliente(request, Cliente.objects.all()), pk=pk)
    
    if request.method == 'POST':
        try:
            nome_cliente = cliente.nome
            cliente.ativo = False
            cliente.save(update_fields=['ativo'])
            messages.success(request, f'Cliente "{nome_cliente}" desactivado com sucesso!')
            return redirect('clientes:lista')
        except Exception as e:
            messages.error(request, f'Erro ao desactivar cliente: {str(e)}')
            return redirect('clientes:detalhes', pk=pk)
    
    context = _ctx(request, 'excluir', {'cliente': cliente})
    return render(request, 'clientes/confirmar_exclusao.html', context)
