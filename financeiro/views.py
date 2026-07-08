import json
import io
import logging
from decimal import Decimal
from django.core.serializers.json import DjangoJSONEncoder
from django.views.generic import ListView, CreateView, DetailView, UpdateView, TemplateView
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q, Count, Prefetch
from django.views.decorators.http import require_POST, require_http_methods

from django.conf import settings

from users.auth_decorators import requer_sessao_ativa
from users.permissoes import _is_admin_ou_acesso_total
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica
from .models import (
    FacturaCliente, ReciboCliente, NotaCredito, NotaDebito,
    FacturaRecibo, HistoricoFinanceiro, registrar_historico,
    RequisicaoFundo, RequisicaoFundoLinha
)
from .forms import (
    FacturaClienteForm, ReciboClienteForm, ReciboClienteUpdateForm,
    NotaCreditoForm, NotaDebitoForm, FacturaReciboForm,
    RequisicaoFundoForm, RequisicaoFundoLinhaForm
)
from utils.format_kz import fmt_kz

logger = logging.getLogger(__name__)


def parse_valor_monetario(valor_str):
    """
    Parse flexível para valores monetários.
    Suporta: 2000000, 2.000.000, 2,000000, 2000000.00, 2.000.000,00, etc.
    """
    try:
        valor_str = valor_str.strip().replace(' ', '')
        
        if not valor_str:
            return Decimal('0')
        
        # Se tem vírgula, é formato europeu (1.234.567,89)
        if ',' in valor_str:
            valor_str = valor_str.replace('.', '').replace(',', '.')
        # Se tem ponto, precisa validar se é separador de milhar ou decimal
        elif '.' in valor_str:
            partes = valor_str.split('.')
            # Se múltiplos pontos OU último grupo tem 3 dígitos (milhar), remove todos
            if len(partes) > 2:
                # Múltiplos pontos = todos são separadores de milhar
                valor_str = valor_str.replace('.', '')
            elif len(partes) == 2 and len(partes[1]) == 3:
                # Último grupo tem 3 dígitos = é separador de milhar
                valor_str = valor_str.replace('.', '')
            # Senão, deixa como está (é decimal tipo 20.00)
        
        return Decimal(valor_str)
    except Exception:
        return Decimal('0')


def _user_tem_acesso_total(request):
    """True se user tem bypass de scoping (Admin ou permissão admin)."""
    from users.permissoes import _is_admin_ou_acesso_total
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return True
    if _is_admin_ou_acesso_total(request):
        return True
    return False


def _tem_escopo_filial(perm_set, filial_id=None):
    """True se o user está escopeado a uma filial (por filial_id ou permissão)."""
    if filial_id:
        return True
    return any(p in (perm_set or set()) for p in ('gerir_filial', 'gerir_financeiro', 'gerir_financeiro_filial',))


def _pode_escrever(request):
    """True se o user pode escrever no módulo financeiro (não é apenas auditor)."""
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel in ('Administrador', 'Despachante Oficial'):
        return True
    from users.permissoes import usuario_tem_permissao, _is_admin_ou_acesso_total
    if _is_admin_ou_acesso_total(request):
        return True
    if usuario_tem_permissao(request, 'acesso_auditoria'):
        return False
    return True


def requer_escrita_financeira(view_func):
    """Decorator: bloqueia acesso de escrita a auditores."""
    def wrapper(request, *args, **kwargs):
        if not _pode_escrever(request):
            messages.error(request, 'Operação não permitida. Auditores têm acesso apenas de leitura.')
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('financeiro:requisicao_lista')
        return view_func(request, *args, **kwargs)
    return wrapper


class BaseContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.session.get('usuario'):
            context['usuario'] = self.request.session['usuario']
            context['papel'] = self.request.session['usuario'].get('papel', '')
            context['nome'] = self.request.session['usuario'].get('nome', '')
        from users.permissoes import get_usuario_permissoes
        context['user_permissoes'] = get_usuario_permissoes(self.request)
        return context

    def _resolve_usuario_id(self):
        """Retorna o usuario_id efectivo para filtragem de dados."""
        banca_usuario_id = self.request.session.get('banca_usuario_id')
        if banca_usuario_id:
            return banca_usuario_id
        return self.request.session.get('usuario_id')

    def _get_user_cliente_filter(self):
        if _user_tem_acesso_total(self.request):
            return {}
        from users.permissoes import get_usuario_permissoes
        perm_set = get_usuario_permissoes(self.request)
        banca_id = self.request.session.get('banca_id')
        if not banca_id:
            usuario_id = self._resolve_usuario_id()
            if not usuario_id:
                return {}
            return {'cliente__usuario_id': usuario_id}
        filtro = {'banca_id': banca_id}
        filial_id = self.request.session.get('colaborador_filial_id')
        if _tem_escopo_filial(perm_set, filial_id) and filial_id:
            filtro['filial_id'] = filial_id
        return filtro

    def _get_user_filter_direct(self):
        if _user_tem_acesso_total(self.request):
            return {}
        from users.permissoes import get_usuario_permissoes
        perm_set = get_usuario_permissoes(self.request)
        banca_id = self.request.session.get('banca_id')
        if not banca_id:
            usuario_id = self._resolve_usuario_id()
            if not usuario_id:
                return {}
            return {'usuario_id': usuario_id}
        filtro = {'banca_id': banca_id}
        filial_id = self.request.session.get('colaborador_filial_id')
        if _tem_escopo_filial(perm_set, filial_id) and filial_id:
            filtro['filial_id'] = filial_id
        return filtro


# ─── Requisições de Fundos ─────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class RequisicaoFundoListView(BaseContextMixin, ListView):
    model = RequisicaoFundo
    template_name = 'financeiro/requisicao_fundo_lista.html'
    context_object_name = 'requisicoes'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'processo_aduaneiro')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_requisicao__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class RequisicaoFundoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = RequisicaoFundo
    form_class = RequisicaoFundoForm
    template_name = 'financeiro/requisicao_fundo_form.html'
    success_message = "Requisição de Fundos criada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:requisicao_detalhe', kwargs={'pk': self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def form_valid(self, form):
        form.instance.criado_por_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.criado_por_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        response = super().form_valid(form)
        self._salvar_custos(self.object)
        registrar_historico(
            'Requisicao', self.object.pk, self.object.numero_requisicao, 'Criada',
            estado_novo='Pendente', valor=self.object.total_geral,
            utilizador_id=self.object.criado_por_id, utilizador_nome=self.object.criado_por_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response

    def _salvar_custos(self, requisicao):
        import re
        prefix = 'custo_'
        custo_indices = set()
        for key in self.request.POST:
            m = re.match(rf'^{prefix}(\d+)_descricao$', key)
            if m:
                custo_indices.add(int(m.group(1)))
        for i in sorted(custo_indices):
            descricao = self.request.POST.get(f'{prefix}{i}_descricao', '').strip()
            if not descricao:
                continue
            documentada = self.request.POST.get(f'{prefix}{i}_documentada') == 'true'
            despesa_tipo = self.request.POST.get(f'{prefix}{i}_despesa_tipo', '').strip()
            valor_raw = self.request.POST.get(f'{prefix}{i}_valor', '0').strip()
            
            logger.debug(f"CUSTO DEBUG [CREATE]: descricao={descricao}, valor_raw='{valor_raw}'")
            
            valor = parse_valor_monetario(valor_raw)
            
            logger.debug(f"CUSTO DEBUG [CREATE]: valor_raw='{valor_raw}' => valor={valor}")
            
            # Honorários do Despachante: mínimo 45.000 KZ
            if despesa_tipo == 'Honorários' and valor < Decimal('45000'):
                valor = Decimal('45000')
            
            documento = self.request.FILES.get(f'{prefix}{i}_documento_justificativo')
            tipo_custo = 'Honorários do Despachante' if despesa_tipo == 'Honorários' else 'Outras Despesas'
            linha = RequisicaoFundoLinha(
                requisicao=requisicao,
                tipo_custo=tipo_custo,
                descricao=descricao,
                documentada=documentada,
                despesa_tipo=despesa_tipo if despesa_tipo else None,
                valor=valor,
                ordem=requisicao.linhas.count() + 1
            )
            if documento:
                linha.documento_justificativo = documento
            linha.save()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Requisição de Fundos"
        context['requisicao'] = context.get('object') or self.object
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
class RequisicaoFundoDetailView(BaseContextMixin, DetailView):
    model = RequisicaoFundo
    template_name = 'financeiro/requisicao_fundo_detalhe.html'
    context_object_name = 'requisicao'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'processo_aduaneiro', 'banca')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Garantir que os totais estão recalculados (compatibilidade com dados antigos)
        self.object._recalcular_totais()
        self.object.save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral'])
        
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        context['linhas'] = self.object.linhas.all().order_by('ordem')
        context['linhas_documentadas'] = self.object.linhas.filter(documentada=True).order_by('ordem')
        context['linhas_nao_documentadas'] = self.object.linhas.filter(documentada=False).order_by('ordem')
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='Requisicao', documento_id=self.object.pk
        )[:20]

        # Verificar se já existe Factura-Recibo associada (via FacturaCliente)
        facturas = self.object.facturas.all()
        context['tem_factura_recibo'] = FacturaRecibo.objects.filter(factura__in=facturas).exists()

        # Formulário inline para adicionar custos
        context['custo_form'] = RequisicaoFundoLinhaForm()
        context['despesas_documentadas'] = RequisicaoFundoLinha.DESPESAS_DOCUMENTADAS
        context['despesas_nao_documentadas'] = RequisicaoFundoLinha.DESPESAS_NAODOCUMENTADAS
        context['despesas_documentadas_json'] = json.dumps(RequisicaoFundoLinha.DESPESAS_DOCUMENTADAS)
        context['despesas_nao_documentadas_json'] = json.dumps(RequisicaoFundoLinha.DESPESAS_NAODOCUMENTADAS)
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class RequisicaoFundoUpdateView(BaseContextMixin, SuccessMessageMixin, UpdateView):
    model = RequisicaoFundo
    form_class = RequisicaoFundoForm
    template_name = 'financeiro/requisicao_fundo_form.html'
    success_message = "Requisição de Fundos actualizada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:requisicao_detalhe', kwargs={'pk': self.object.pk})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs
    
    def get_form(self, form_class=None):
        """Bloqueia edição de requisições em estado final"""
        form = super().get_form(form_class)
        
        # Bloquear edição se requisição não está em Pendente
        if self.object and self.object.estado != 'Pendente':
            for field in form.fields:
                form.fields[field].disabled = True
                form.fields[field].widget.attrs['readonly'] = True
        
        return form
    
    def form_valid(self, form):
        # Verificar se requisição está em estado editável
        if self.object.estado != 'Pendente':
            from django.contrib import messages
            messages.error(self.request, 
                f"Não é possível editar uma requisição em estado {self.object.get_estado_display()}")
            return self.form_invalid(form)
        
        response = super().form_valid(form)
        self._salvar_custos(self.object)
        return response

    def _salvar_custos(self, requisicao):
        import re
        prefix = 'custo_'
        custo_indices = set()
        for key in self.request.POST:
            m = re.match(rf'^{prefix}(\d+)_descricao$', key)
            if m:
                custo_indices.add(int(m.group(1)))
        for i in sorted(custo_indices):
            descricao = self.request.POST.get(f'{prefix}{i}_descricao', '').strip()
            if not descricao:
                continue
            documentada = self.request.POST.get(f'{prefix}{i}_documentada') == 'true'
            despesa_tipo = self.request.POST.get(f'{prefix}{i}_despesa_tipo', '').strip()
            valor_raw = self.request.POST.get(f'{prefix}{i}_valor', '0').strip()
            
            logger.debug(f"CUSTO DEBUG [UPDATE]: descricao={descricao}, valor_raw='{valor_raw}'")
            
            valor = parse_valor_monetario(valor_raw)
            
            logger.debug(f"CUSTO DEBUG [UPDATE]: valor_raw='{valor_raw}' => valor={valor}")
            
            # Honorários do Despachante: mínimo 45.000 KZ
            if despesa_tipo == 'Honorários' and valor < Decimal('45000'):
                valor = Decimal('45000')
            
            documento = self.request.FILES.get(f'{prefix}{i}_documento_justificativo')
            tipo_custo = 'Honorários do Despachante' if despesa_tipo == 'Honorários' else 'Outras Despesas'
            linha = RequisicaoFundoLinha(
                requisicao=requisicao,
                tipo_custo=tipo_custo,
                descricao=descricao,
                documentada=documentada,
                despesa_tipo=despesa_tipo if despesa_tipo else None,
                valor=valor,
                ordem=requisicao.linhas.count() + 1
            )
            if documento:
                linha.documento_justificativo = documento
            linha.save()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Editar Requisição de Fundos"
        context['requisicao'] = context.get('object') or self.object
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        context['bloqueado'] = self.object and self.object.estado != 'Pendente'
        return context


@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_requisicao(request, pk):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    
    if requisicao.estado == 'Anulada':
        messages.error(request, 'Esta requisição já está anulada.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    if requisicao.facturas.exists():
        messages.error(request, 'Não é possível anular uma requisição que já possui Factura Final associada.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Anulada'
        requisicao.save(update_fields=['estado'])
        
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Anulada',
            estado_anterior=estado_anterior, estado_novo='Anulada',
            valor=requisicao.total_geral,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
            banca_id=requisicao.banca_id, filial_id=requisicao.filial_id,
        )
        messages.success(request, f'Requisição {requisicao.numero_requisicao} anulada com sucesso.')
    
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
@require_POST
def eliminar_requisicao(request, pk):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    
    if requisicao.facturas.exists():
        messages.error(request, 'Não é possível eliminar uma requisição que já possui Factura Final associada.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    numero = requisicao.numero_requisicao
    requisicao.delete()
    messages.success(request, f'Requisição {numero} eliminada com sucesso.')
    return redirect('financeiro:requisicao_lista')


@requer_sessao_ativa
@requer_escrita_financeira
def aceitar_requisicao(request, pk):
    """Marca a Requisição de Fundos como Aceite pelo cliente"""
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    
    if requisicao.estado != 'Pendente':
        messages.error(request, 'Apenas requisições Pendentes podem ser aceites.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Aceite'
        requisicao.save(update_fields=['estado'])
        
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Aceite pelo cliente',
            estado_anterior=estado_anterior, estado_novo='Aceite',
            valor=requisicao.total_geral,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
            banca_id=requisicao.banca_id, filial_id=requisicao.filial_id,
        )
        messages.success(request, f'Requisição {requisicao.numero_requisicao} aceite com sucesso.')
    
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
def rejeitar_requisicao(request, pk):
    """Marca a Requisição de Fundos como Rejeitada pelo cliente"""
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    
    if requisicao.estado != 'Pendente':
        messages.error(request, 'Apenas requisições Pendentes podem ser rejeitadas.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Rejeitada'
        requisicao.save(update_fields=['estado'])
        
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Rejeitada pelo cliente',
            estado_anterior=estado_anterior, estado_novo='Rejeitada',
            valor=requisicao.total_geral,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
            banca_id=requisicao.banca_id, filial_id=requisicao.filial_id,
        )
        messages.success(request, f'Requisição {requisicao.numero_requisicao} rejeitada.')
    
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
def adicionar_linha_requisicao(request, pk):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
    
    if requisicao.estado in ('Anulada', 'Aceite', 'Rejeitada'):
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Não é possível adicionar linhas a uma requisição neste estado.'})
        messages.error(request, 'Não é possível adicionar linhas a uma requisição neste estado.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method != 'POST':
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Método não permitido.'})
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    form = RequisicaoFundoLinhaForm(request.POST, request.FILES)
    if form.is_valid():
        ajustado = getattr(form, '_valor_auto_corrigido', False)
        linha = form.save(commit=False)
        linha.requisicao = requisicao
        linha.ordem = requisicao.linhas.count() + 1
        linha.save()

        requisicao._recalcular_totais()
        requisicao.save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral'])

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': 'Linha adicionada com sucesso.',
                'auto_ajustado': ajustado,
                'linha': {
                    'id': linha.id,
                    'despesa_tipo': linha.despesa_tipo,
                    'descricao': linha.descricao,
                    'documentada': linha.documentada,
                    'valor': float(linha.valor),
                    'has_documento': bool(linha.documento_justificativo),
                    'documento_url': linha.documento_justificativo.url if linha.documento_justificativo else None,
                },
                'totais': {
                    'subtotal_geral': float(requisicao.subtotal_geral),
                    'iva_honorarios': float(requisicao.iva_honorarios),
                    'retencao': float(requisicao.retencao),
                    'total_geral': float(requisicao.total_geral),
                }
            })

        if ajustado:
            messages.info(request, 'O valor mínimo para Honorários do Despachante é 45.000 KZ — o valor foi ajustado automaticamente.')
        messages.success(request, 'Linha adicionada com sucesso.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if is_ajax:
        erros = []
        for field, msgs in form.errors.items():
            for msg in msgs:
                erros.append(f'{field}: {msg}')
        return JsonResponse({'success': False, 'errors': erros})

    for error in form.errors.values():
        for msg in error:
            messages.error(request, msg)
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
def editar_linha_requisicao(request, pk, linha_id):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    linha = get_object_or_404(RequisicaoFundoLinha, pk=linha_id, requisicao=requisicao)
    
    if requisicao.estado in ('Anulada', 'Aceite', 'Rejeitada'):
        messages.error(request, 'Não é possível editar linhas de uma requisição neste estado.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method != 'POST':
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    form = RequisicaoFundoLinhaForm(request.POST, request.FILES, instance=linha)
    if form.is_valid():
        if getattr(form, '_valor_auto_corrigido', False):
            messages.info(request, 'O valor mínimo para Honorários do Despachante é 45.000 KZ — o valor foi ajustado automaticamente.')
        form.save()
        messages.success(request, 'Linha actualizada com sucesso.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    for error in form.errors.values():
        for msg in error:
            messages.error(request, msg)
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
@require_POST
def eliminar_linha_requisicao(request, pk, linha_id):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    linha = get_object_or_404(RequisicaoFundoLinha, pk=linha_id, requisicao=requisicao)
    
    if requisicao.estado in ('Anulada', 'Aceite', 'Rejeitada'):
        messages.error(request, 'Não é possível eliminar linhas de uma requisição neste estado.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    linha.delete()
    
    # Recalcular totais
    requisicao._recalcular_totais()
    requisicao.save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral'])
    
    messages.success(request, 'Linha removida com sucesso.')
    return redirect('financeiro:requisicao_detalhe', pk=pk)


@requer_sessao_ativa
def requisicao_pdf(request, pk):
    """Gera PDF da Requisição de Fundos com layout profissional e dados reais"""
    from datetime import datetime
    from decimal import Decimal
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from users.models import Usuario
    
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    buffer = io.BytesIO()
    
    PAGE_W, PAGE_H = A4
    MARGIN = 0.7 * cm
    W = PAGE_W - 2 * MARGIN
    
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title=f"Requisição de Fundos {requisicao.numero_requisicao}",
    )
    
    # Cores
    COR_PRETO = colors.HexColor('#0f172a')
    COR_CINZA = colors.HexColor('#64748b')
    COR_VERDE = colors.HexColor('#059669')
    COR_BORDA = colors.HexColor('#cbd5e1')
    COR_VERMELHO = colors.HexColor('#dc2626')
    
    # Estilos
    def st(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRETO, leading=11)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)
    
    s_small = st('small', fontSize=6.5, textColor=COR_CINZA, leading=8)
    s_normal = st('normal', fontSize=8, leading=9)
    
    banca = requisicao.banca
    cliente = requisicao.cliente
    processo = requisicao.processo_aduaneiro
    
    # Buscar nome do despachante responsável (dono da banca)
    responsavel_nome = 'DESPACHANTE OFICIAL'
    if banca:
        try:
            usuario_banca = Usuario.objects.get(id=banca.usuario_id)
            responsavel_nome = (usuario_banca.nome or 'DESPACHANTE OFICIAL').upper()
        except:
            responsavel_nome = 'DESPACHANTE OFICIAL'
    
    story = []
    
    # CABEÇALHO: Data, hora na parte superior direita
    agora = datetime.now()
    top_line = Table([[
        Paragraph(f'', st('empty')),
        Paragraph(f'<font size="6.5" color="#999">Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>', st('top', alignment=TA_RIGHT, fontSize=6.5))
    ]], colWidths=[W * 0.6, W * 0.4])
    top_line.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(top_line)
    story.append(Spacer(1, 0.1 * cm))
    
    story.append(Spacer(1, 0.1 * cm))
    
    # LOGO E NIF
    nif_txt = f"NIF: {banca.nif}" if banca else 'N/D'
    nome_txt = banca.nome if banca else 'Despachante Oficial'
    
    header_table = Table([[
        Paragraph(f'<font size="10"><b>{nome_txt}</b></font>', st('nome', fontName='Helvetica-Bold', fontSize=10.5)),
        Paragraph(f'<font size="8" color="#666"><b>{nif_txt}</b></font>', st('nif', fontSize=8, alignment=TA_RIGHT))
    ]], colWidths=[W * 0.7, W * 0.3])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(header_table)
    
    # DESPACHANTE RESPONSÁVEL EM VERDE E BOLD
    story.append(Paragraph(
        f'<font size="9" color="#059669"><b>{responsavel_nome}</b></font>',
        st('resp', fontName='Helvetica-Bold', fontSize=9)
    ))
    story.append(Spacer(1, 0.05 * cm))
    
    # Info: Banca - HASH e outros dados
    story.append(Paragraph(
        f'<font size="7"><b>{nome_txt} - HASH</b></font>',
        st('hash', fontName='Helvetica-Bold', fontSize=7)
    ))
    story.append(Paragraph(
        '<font size="6.5">Processado por programa válido nº35/AGT/2019</font>',
        s_small
    ))
    
    # Endereço e contatos
    endereco = banca.endereco if banca else ''
    telefone = banca.telefone if banca else ''
    email_b = banca.email if banca else ''
    cdoa = banca.licenca_cdoa if banca else ''
    
    for info in filter(None, [endereco, 'ANGOLA', f'Tel: {telefone}' if telefone else '', f'Email: {email_b}' if email_b else '', f'Cédula CDOA: {cdoa}' if cdoa else '']):
        story.append(Paragraph(f'<font size="6.5" color="#666">{info}</font>', s_small))
    
    story.append(Spacer(1, 0.15 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.15 * cm))
    
    story.append(Spacer(1, 0.15 * cm))
    
    # REQUISIÇÃO Nº E DATA
    data_emissao = requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else 'N/D'
    
    req_table = Table([[
        Paragraph(f'<font size="9.5"><b>Requisição Nº: {requisicao.numero_requisicao}</b></font>', st('req', fontName='Helvetica-Bold', fontSize=9.5)),
        Paragraph(f'<font size="9.5"><b>Data: {data_emissao}</b></font>', st('data', fontName='Helvetica-Bold', fontSize=9.5, alignment=TA_RIGHT))
    ]], colWidths=[W * 0.55, W * 0.45])
    req_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(req_table)
    story.append(Spacer(1, 0.15 * cm))
    
    story.append(Spacer(1, 0.15 * cm))
    
    # TABELA DE 3 COLUNAS: Designação | Direitos | Despesas Inerentes
    valor_aduaneiro = processo.valor_total if processo and hasattr(processo, 'valor_total') else requisicao.valor_cif or Decimal('0')
    
    # Coluna 1: Designação
    designacao_text = f"""<b>Designação da mercadoria</b>

Pelo desembarque de:
<b>{requisicao.mercadoria_descricao or (processo.descricao_mercadoria if processo else 'N/D')}</b>

<b>Documentos</b>
BL ou Carta: {requisicao.numero_bl_awb or '—'}
Procedência: {requisicao.origem or '—'}
Navio/Avião: {requisicao.meio_transporte or '—'}
Nr DU: {processo.numero_du if processo else '—'}
Valor CIF: {fmt_kz(requisicao.valor_cif) if requisicao.valor_cif else '—'}
Câmbio: {requisicao.cambio_referencia or '—'}
Valor aduaneiro: {fmt_kz(valor_aduaneiro)}"""
    
    # Coluna 2: Direitos e mais imposições (DOCUMENTADAS)
    despesas_doc = requisicao.linhas.filter(documentada=True)
    total_direitos = Decimal('0')
    direitos_text = '<b>Direitos e mais imposições</b>\n\n'
    
    for linha in despesas_doc:
        if linha.valor and linha.valor > 0:
            direitos_text += f"{linha.despesa_tipo or 'Despesa'} ..... {fmt_kz(linha.valor)}\n"
            total_direitos += linha.valor
    
    if total_direitos == 0:
        direitos_text += "EP 14 .................\nEP 15 .................\nEP 17 ..................."
    
    # Coluna 3: Despesas inerentes (NÃO DOCUMENTADAS)
    despesas_nao_doc = requisicao.linhas.filter(documentada=False)
    total_despesas = Decimal('0')
    despesas_text = '<b>Despesas inerentes</b>\n\n'
    
    for linha in despesas_nao_doc:
        if linha.valor and linha.valor > 0:
            despesas_text += f"{linha.despesa_tipo or 'Despesa'} ..... {fmt_kz(linha.valor)}\n"
            total_despesas += linha.valor
    
    if total_despesas == 0:
        despesas_text += "Honorários: —"
    
    # Criar tabela 3 colunas
    tres_colunas = Table([[
        Paragraph(designacao_text, st('designacao', fontSize=6.5, leading=8)),
        Paragraph(direitos_text, st('direitos', fontSize=6.5, leading=8)),
        Paragraph(despesas_text, st('despesas', fontSize=6.5, leading=8))
    ]], colWidths=[W/3 - 0.15*cm, W/3 - 0.15*cm, W/3 - 0.15*cm])
    
    tres_colunas.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.75, COR_BORDA),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tres_colunas)
    story.append(Spacer(1, 0.15 * cm))
    story.append(Spacer(1, 0.15 * cm))
    
    # TOTALIZAÇÕES EM VERMELHO
    cambio = Decimal(requisicao.cambio_referencia or 1)
    if cambio == 0:
        cambio = Decimal(1)
    valor_usd = requisicao.total_geral / cambio if requisicao.total_geral else Decimal('0')
    
    totais = Table([
        [Paragraph('<font size="7"><b>Mercadorias</b></font>', st('tot')), Paragraph(f'<font size="7" color="{COR_VERMELHO}"><b>{fmt_kz(total_direitos)}</b></font>', st('tot')), 
         Paragraph('<font size="7"><b>Serviços</b></font>', st('tot')), Paragraph(f'<font size="7" color="{COR_VERMELHO}"><b>{fmt_kz(total_despesas)}</b></font>', st('tot'))],
        [Paragraph('<font size="7">Outros</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot')), 
         Paragraph('<font size="7">IEC</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot'))],
        [Paragraph('<font size="7">Retenção</font>', st('tot')), Paragraph(f'<font size="7">{fmt_kz(requisicao.retencao) if requisicao.retencao else "0,00"}</font>', st('tot')), 
         Paragraph('<font size="7">Descontos</font>', st('tot')), Paragraph(f'<font size="7">0,00</font>', st('tot'))],
        [Paragraph('<font size="7"><b>TOTAL Kz:</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph(f'<font size="8" color="{COR_VERMELHO}"><b>{fmt_kz(requisicao.total_geral or 0)}</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph('<font size="7"><b>TOTAL USD:</b></font>', st('tot', fontName='Helvetica-Bold')), 
         Paragraph(f'<font size="8" color="{COR_VERMELHO}"><b>{fmt_kz(valor_usd)}</b></font>', st('tot', fontName='Helvetica-Bold'))],
    ], colWidths=[2.2*cm, 2.5*cm, 2.2*cm, 2.5*cm])
    
    totais.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(totais)
    story.append(Spacer(1, 0.2 * cm))
    
    # NOTA
    story.append(Paragraph(
        '<font size="6.5"><i>NOTA: Os originais das contas referidas vão devediamente selecionadas pelo valor dos honorários</i></font>',
        st('nota', fontSize=6.5, alignment=TA_CENTER)
    ))
    story.append(Spacer(1, 0.2 * cm))
    
    # ASSINATURA
    assinatura = Table([
        [Paragraph('Recebeu em: _____/_____/______', st('ass', fontSize=7)), 
         Paragraph('O Cliente', st('ass', fontSize=7, alignment=TA_CENTER))],
        [Paragraph('', st('ass', fontSize=1)), 
         Paragraph(f'<b>{responsavel_nome}</b>', st('ass', fontSize=7.5, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ], colWidths=[W/2, W/2])
    
    assinatura.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(assinatura)
    story.append(Spacer(1, 0.15 * cm))
    
    # DADOS DO CLIENTE (FINAL)
    cliente_nome = cliente.nome if cliente else 'Nome do Cliente'
    cliente_loc = cliente.localizacao if cliente else 'Endereço'
    cliente_tel = cliente.telefone if cliente else 'Telefone'
    
    story.append(Paragraph(f'<font size="8"><b>{cliente_nome}</b></font>', st('cli', fontName='Helvetica-Bold', fontSize=8)))
    story.append(Paragraph(f'<font size="6.5">{cliente_loc} - Tel {cliente_tel}</font>', s_small))
    
    # BUILD DO PDF
    doc.build(story)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Requisicao_{requisicao.numero_requisicao}.pdf"'
    return response


@requer_sessao_ativa
def requisicao_enviar_email(request, pk):
    """Envia a Requisição de Fundos por email com PDF anexado (novo design)"""
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    cliente = requisicao.cliente
    
    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        # Gerar PDF usando a nova função
        buffer = io.BytesIO()
        
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage
        from reportlab.platypus.flowables import HRFlowable
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=0.8*cm, rightMargin=0.8*cm,
            topMargin=0.8*cm, bottomMargin=1.5*cm,
            title=f"Requisição de Fundos {requisicao.numero_requisicao}",
        )
        W = A4[0] - 1.6*cm
        
        # ─── Cores ──────────────────────────────────────────────────────────────
        cor_cabecalho = colors.HexColor('#0f172a')
        cor_primaria = colors.HexColor('#137fec')
        cor_cinza_claro = colors.HexColor('#f1f5f9')
        cor_borda = colors.HexColor('#cbd5e1')
        cor_linha_par = colors.HexColor('#f8fafc')
        
        # ─── Estilos ────────────────────────────────────────────────────────────
        s_small = ParagraphStyle('small', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#64748b'), leading=10)
        
        story = []
        
        # ─── CABEÇALHO ───────────────────────────────────────────────────────────
        banca = requisicao.banca
        logo_path = None
        if banca and hasattr(banca, 'logo') and banca.logo:
            logo_path = banca.logo.path
        
        col1 = []
        if logo_path:
            try:
                img = RLImage(logo_path, width=2.2*cm, height=1.5*cm)
                col1.append(img)
            except:
                col1.append(Paragraph('', s_small))
        else:
            col1.append(Paragraph('', s_small))
        
        col2_text = f"""<b>{banca.nome if banca else 'Banca'}</b><br/>
<font size="7">NIF: {banca.nif if banca and hasattr(banca, 'nif') else 'N/D'}<br/>
Licença CDOA: {banca.licenca_cdoa if banca and hasattr(banca, 'licenca_cdoa') and banca.licenca_cdoa else 'N/D'}<br/>
{banca.endereco if banca and hasattr(banca, 'endereco') else ''}<br/>
Tel: {banca.telefone if banca and hasattr(banca, 'telefone') else 'N/D'}<br/>
Email: {banca.email if banca and hasattr(banca, 'email') else 'N/D'}</font>"""
        col2 = [Paragraph(col2_text, ParagraphStyle('banca_info', fontSize=10, fontName='Helvetica', textColor=cor_cabecalho, leading=12))]
        
        col3_text = f"""<b>REQUISIÇÃO DE FUNDOS</b><br/>
<font size="8">Nº: {requisicao.numero_requisicao}<br/>
Data: {requisicao.data_emissao.strftime('%d/%m/%Y')}<br/>
Validade: {requisicao.data_validade.strftime('%d/%m/%Y')}</font>"""
        col3 = [Paragraph(col3_text, ParagraphStyle('doc_info', fontSize=10, fontName='Helvetica-Bold', textColor=cor_primaria, leading=12, alignment=TA_RIGHT))]
        
        t_cabecalho = Table([[col1, col2, col3]], colWidths=[2.5*cm, W/2 - 1.25*cm, W/2 - 1.25*cm])
        t_cabecalho.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ]))
        story.append(t_cabecalho)
        story.append(Spacer(1, 0.3*cm))
        
        # ─── TABELA DE CUSTOS ────────────────────────────────────────────────────
        story.append(Paragraph('<b>DISCRIMINAÇÃO DE CUSTOS</b>', ParagraphStyle('tab_titulo', fontSize=10, fontName='Helvetica-Bold', textColor=cor_primaria, spaceAfter=6)))
        
        linhas_tabela = [['Item', 'Descrição', 'Tipo', 'Doc.', 'Valor (KZ)']]
        
        for idx, linha in enumerate(requisicao.linhas.all().order_by('ordem'), 1):
            desc = linha.descricao[:40] + ('...' if len(linha.descricao) > 40 else '')
            doc_label = 'Sim' if linha.documentada else 'Não'
            linhas_tabela.append([
            str(idx), desc, linha.despesa_tipo or '—', doc_label, fmt_kz(linha.valor or 0)
            ])
        
        if len(linhas_tabela) == 1:
            linhas_tabela.append(['', 'Sem custos adicionados', '', '', '0,00 KZ'])
        
        col_widths = [0.8*cm, W/2 - 0.4*cm, 2.5*cm, 1.2*cm, 2.2*cm]
        t_custos = Table(linhas_tabela, colWidths=col_widths)
        t_custos.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
            ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('ALIGN', (3, 1), (3, -1), 'CENTER'),
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t_custos)
        story.append(Spacer(1, 0.4*cm))
        
        # ─── TOTAL ──────────────────────────────────────────────────────────────
        t_total = Table([
            ['TOTAL GERAL A PAGAR', fmt_kz(requisicao.total_geral or 0)]
        ], colWidths=[W - 3*cm, 3*cm])
        t_total.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), cor_cabecalho),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(t_total)
        
        doc.build(story)
        buffer.seek(0)
        
        anexos = [(f'Requisicao_{requisicao.numero_requisicao}.pdf', buffer.read(), 'application/pdf')]
        
        assunto = f"Requisição de Fundos {requisicao.numero_requisicao} – SICDOA"
        
        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Requisição de Fundos referente ao seu processo aduaneiro.

Detalhes da Requisição:
  Número: {requisicao.numero_requisicao}
  Data de Emissão: {requisicao.data_emissao.strftime('%d/%m/%Y')}
  Data de Validade: {requisicao.data_validade.strftime('%d/%m/%Y')}
  Processo Aduaneiro: {requisicao.processo_aduaneiro.numero_du if requisicao.processo_aduaneiro else 'N/D'}
  
Totalizações:
  Subtotal Geral: {fmt_kz(requisicao.subtotal_geral)} KZ
  IVA (14% Honorários): {fmt_kz(requisicao.iva_honorarios)} KZ
  Retenção (6.5% Honorários): {fmt_kz(requisicao.retencao)} KZ
  Total Geral a Pagar: {fmt_kz(requisicao.total_geral)} KZ

Esta Requisição de Fundos é equivalente a uma Fatura Proforma e não é documento contabilístico final, estando sujeita a alterações conforme a execução do despacho.

Agradecemos a sua atenção.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Requisição de Fundos</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Requisição de Fundos referente ao seu processo aduaneiro.</p>
            
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
                    <td style="padding: 10px;">{requisicao.numero_requisicao}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data de Emissão:</td>
                    <td style="padding: 10px;">{requisicao.data_emissao.strftime('%d/%m/%Y')}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data de Validade:</td>
                    <td style="padding: 10px;">{requisicao.data_validade.strftime('%d/%m/%Y')}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Processo Aduaneiro:</td>
                    <td style="padding: 10px;">{requisicao.processo_aduaneiro.numero_du if requisicao.processo_aduaneiro else 'N/D'}</td>
                </tr>
            </table>

            <h3 style="color: #0f172a; margin-top: 20px;">Totalizações:</h3>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; color: #475569;">Subtotal Geral:</td>
                    <td style="padding: 10px; text-align: right;">{fmt_kz(requisicao.subtotal_geral)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; color: #475569;">IVA (14% Honorários):</td>
                    <td style="padding: 10px; text-align: right;">{fmt_kz(requisicao.iva_honorarios)} KZ</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; color: #475569;">Retenção (6.5% Honorários):</td>
                    <td style="padding: 10px; text-align: right;">{fmt_kz(requisicao.retencao)} KZ</td>
                </tr>
                <tr style="border-bottom: 2px solid #137fec;">
                    <td style="padding: 12px; font-weight: bold; color: #0f172a;">Total Geral a Pagar:</td>
                    <td style="padding: 12px; text-align: right; font-weight: bold; color: #137fec; font-size: 16px;">{fmt_kz(requisicao.total_geral)} KZ</td>
                </tr>
            </table>

            <div style="margin-top: 20px; padding: 15px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 4px;">
                <p style="margin: 0; color: #92400e; font-size: 12px;">
                    <strong>Nota:</strong> Esta Requisição de Fundos é equivalente a uma Fatura Proforma e não é documento contabilístico final, estando sujeita a alterações conforme as diretrizes da AGT.
                </p>
            </div>

            <p style="margin-top: 25px;">Agradecemos a sua atenção.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Requisição {requisicao.numero_requisicao} enviada por e-mail para {cliente.email} com sucesso.')
        
        # Registrar ação no histórico
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Email Enviado',
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
            banca_id=requisicao.banca_id, filial_id=requisicao.filial_id,
        )
    except Exception as e:
        logger.exception(f"Erro ao enviar email da requisição {requisicao.pk}")
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:requisicao_detalhe', pk=pk)


# ─── Facturas a partir de Requisições de Fundos ────────────────────────────────

@requer_sessao_ativa
@requer_escrita_financeira
def criar_factura_de_requisicao(request, pk):
    """Cria uma Factura Final a partir de uma Requisição de Fundos (Fatura Pró-forma)"""
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    
    # Verificar se já existe factura para esta requisição
    if requisicao.facturas.exists():
        messages.warning(request, 'Já existe uma Factura associada a esta Requisição.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    if requisicao.estado != 'Aceite':
        messages.error(request, 'Apenas requisições Aceites pelo cliente podem gerar Factura Final.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)
    
    def _mapear_linhas(linhas_qs):
        """Classifica as linhas da RF nos campos da FacturaCliente
        
        Regras:
        - Honorários do Despachante (tipo_custo ou despesa_tipo ~ Honorários) → honorarios
        - Despesas documentadas com perfil fiscal/taxas → taxas_aduaneiras
        - Despesas documentadas portuárias/terminais → emolumentos
        - Restantes (não-documentadas operacionais, etc.) → despesas_operacionais
        """
        DESP_TAXAS = {'Direitos Aduaneiros', 'Taxa Administrativa', 'Inspeção Sanitária',
                       'Multas e Desdobramento', 'Multas'}
        DESP_EMOL = {'JUP', 'Factura de Exportação', 'Emissão DAR'}
        
        honorarios = Decimal('0')
        taxas_aduaneiras = Decimal('0')
        emolumentos = Decimal('0')
        despesas_operacionais = Decimal('0')
        
        for linha in linhas_qs:
            valor = linha.valor or Decimal('0')
            if not valor:
                continue
            tc = (linha.tipo_custo or '').strip()
            dt = (linha.despesa_tipo or '').strip()
            
            # Honorários — por tipo_custo ou despesa_tipo
            if tc == 'Honorários do Despachante' or dt.startswith('Honorário'):
                honorarios += valor
            elif tc == 'Impostos e Taxas Aduaneiras (AGT)':
                taxas_aduaneiras += valor
            elif tc == 'Despesas Portuárias e Terminais':
                emolumentos += valor
            elif tc in ('Logística e Transporte', 'Outros') or not tc:
                # Classificar por despesa_tipo quando tipo_custo é genérico
                if dt in DESP_TAXAS:
                    taxas_aduaneiras += valor
                elif dt in DESP_EMOL:
                    emolumentos += valor
                else:
                    despesas_operacionais += valor
            else:
                despesas_operacionais += valor
        
        iva = (honorarios * Decimal('0.14')).quantize(Decimal('0.01'))
        valor_total = honorarios + taxas_aduaneiras + emolumentos + despesas_operacionais + iva
        
        return honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, valor_total
    
    def _numero_extenso(num):
        """Converte número para extenso em português (até 999 milhões)"""
        if num == 0:
            return 'zero kwanzas'
        unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
        dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
        teens = ['dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove']
        centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
        def ate_999(n):
            if n == 0: return ''
            if n < 10: return unidades[n]
            if n < 20: return teens[n - 10]
            if n < 100:
                d, u = divmod(n, 10)
                return dezenas[d] + (' e ' + unidades[u] if u else '')
            c, r = divmod(n, 100)
            if c == 1 and r == 0: return 'cem'
            return centenas[c] + (' e ' + ate_999(r) if r else '')
        try:
            total = int(num)
            if total == 0: return 'zero kwanzas'
            if total >= 1_000_000:
                m, r = divmod(total, 1_000_000)
                txt = ('um milhão' if m == 1 else ate_999(m) + ' milhões')
                if r: txt += ' e ' + ate_999(r)
                return (txt + ' kwanzas').capitalize()
            if total >= 1000:
                m, r = divmod(total, 1000)
                txt = 'mil' if m == 1 else ate_999(m) + ' mil'
                if r: txt += ' e ' + ate_999(r)
                return (txt + ' kwanzas').capitalize()
            return (ate_999(total) + ' kwanzas').capitalize()
        except Exception:
            return f'{num} kwanzas'
    
    if request.method == 'POST':
        honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, _ = _mapear_linhas(requisicao.linhas.all())
        
        factura = FacturaCliente(
            cliente=requisicao.cliente,
            processo_aduaneiro=requisicao.processo_aduaneiro,
            honorarios_despachante=honorarios,
            taxas_aduaneiras=taxas_aduaneiras,
            emolumentos=emolumentos,
            despesas_operacionais=despesas_operacionais,
            iva=iva,
            data_vencimento=requisicao.data_validade,
            descricao=f'Factura Final referente a Requisição de Fundos {requisicao.numero_requisicao}',
            criado_por_id=request.session.get('usuario_id'),
            criado_por_nome=request.session.get('usuario', {}).get('nome', ''),
            banca_id=requisicao.banca_id,
            filial_id=requisicao.filial_id,
            requisicao_fundo=requisicao,
        )
        factura.save()
        
        # Registrar no histórico
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'FacturaCliente', factura.pk, factura.numero_factura, 'Criada de Requisição',
            valor=factura.valor_total,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=factura.cliente.nome,
            banca_id=factura.banca_id, filial_id=factura.filial_id,
        )
        
        messages.success(request, f'Factura {factura.numero_factura} criada com sucesso a partir da Requisição.')
        return redirect('financeiro:factura_detalhe', pk=factura.pk)
    
    # GET - mostrar confirmação
    honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, valor_total = _mapear_linhas(requisicao.linhas.all())
    
    # Calcular próximo número de factura
    ano = timezone.now().year
    ultimo = FacturaCliente.objects.filter(numero_factura__startswith=f'FT-{ano}-').order_by('-numero_factura').first()
    prox_seq = 1
    if ultimo and ultimo.numero_factura:
        try:
            prox_seq = int(ultimo.numero_factura.split('-')[-1]) + 1
        except ValueError:
            pass
    proximo_numero_factura = f'FT-{ano}-{prox_seq:04d}'
    
    context = {
        'requisicao': requisicao,
        'proximo_numero_factura': proximo_numero_factura,
        'honorarios': fmt_kz(honorarios),
        'taxas_aduaneiras': fmt_kz(taxas_aduaneiras),
        'emolumentos': fmt_kz(emolumentos),
        'despesas_operacionais': fmt_kz(despesas_operacionais),
        'iva': fmt_kz(iva),
        'valor_total': fmt_kz(valor_total),
        'valor_total_extenso': _numero_extenso(int(valor_total)),
        'linhas': requisicao.linhas.all(),
        'active_menu': 'Financeiro',
        'active_sub': 'requisicoes',
    }
    if request.session.get('usuario'):
        context['usuario'] = request.session['usuario']
        context['papel'] = request.session['usuario'].get('papel', '')
        context['nome'] = request.session['usuario'].get('nome', '')
    
    return render(request, 'financeiro/criar_factura_de_requisicao.html', context)


@requer_sessao_ativa
@requer_escrita_financeira
def requisicao_criar_factura_recibo(request, pk):
    """Cria uma Factura-Recibo a partir de uma Requisição de Fundos"""
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)

    if requisicao.estado != 'Aceite':
        messages.error(request, 'Apenas requisições Aceites podem gerar Factura-Recibo.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    factura = requisicao.facturas.first()

    if not factura:
        messages.error(request, 'A Requisição não possui uma Factura Final associada. Crie a Factura Final primeiro.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method == 'POST':
        forma_pagamento = request.POST.get('forma_pagamento', '').strip()
        data_str = request.POST.get('data', '').strip()

        erros = []
        if not forma_pagamento:
            erros.append('Selecione a forma de pagamento.')
        if not data_str:
            erros.append('Informe a data.')

        if erros:
            for e in erros:
                messages.error(request, e)
        else:
            from datetime import datetime as dt
            data = dt.strptime(data_str, '%Y-%m-%d').date()

            if data > timezone.now().date():
                messages.error(request, 'A data não pode estar no futuro.')
            else:
                recibo = FacturaRecibo(
                    banca=requisicao.banca,
                    filial=requisicao.filial,
                    cliente=requisicao.cliente,
                    factura=factura,
                    requisicao_fundo=requisicao,
                    valor=requisicao.total_geral,
                    forma_pagamento=forma_pagamento,
                    data=data,
                    estado='Paga',
                    utilizador_responsavel_id=request.session.get('usuario_id'),
                    utilizador_responsavel_nome=request.session.get('usuario', {}).get('nome', ''),
                )
                recibo.save()

                registrar_historico(
                    'FacturaRecibo', recibo.pk, recibo.numero_factura_recibo, 'Criada de Requisição',
                    valor=recibo.valor,
                    utilizador_id=recibo.utilizador_responsavel_id,
                    utilizador_nome=recibo.utilizador_responsavel_nome,
                    cliente_nome=recibo.cliente.nome,
                    banca_id=recibo.banca_id,
                    filial_id=recibo.filial_id,
                )

                messages.success(request, f'Factura-Recibo {recibo.numero_factura_recibo} emitida com sucesso.')
                return redirect('financeiro:factura_recibo_detalhe', pk=recibo.pk)

    context = {
        'requisicao': requisicao,
        'factura': factura,
        'hoje': timezone.now().strftime('%Y-%m-%d'),
        'active_menu': 'Financeiro',
        'active_sub': 'requisicoes',
    }
    if request.session.get('usuario'):
        context['usuario'] = request.session['usuario']
        context['papel'] = request.session['usuario'].get('papel', '')
        context['nome'] = request.session['usuario'].get('nome', '')
    return render(request, 'financeiro/criar_factura_recibo_de_requisicao.html', context)


def _user_tem_acesso_total(request):
    """True se user tem bypass de scoping (Admin ou permissÃ£o admin)."""
    from users.permissoes import _is_admin_ou_acesso_total
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel == 'Administrador':
        return True
    if _is_admin_ou_acesso_total(request):
        return True
    return False


def _tem_escopo_filial(perm_set, filial_id=None):
    """True se o user estÃ¡ escopeado a uma filial (por filial_id ou permissÃ£o)."""
    if filial_id:
        return True
    return any(p in (perm_set or set()) for p in ('gerir_filial', 'gerir_financeiro', 'gerir_financeiro_filial',))


def _pode_escrever(request):
    """True se o user pode escrever no mÃ³dulo financeiro (nÃ£o Ã© apenas auditor)."""
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel in ('Administrador', 'Despachante Oficial'):
        return True
    from users.permissoes import usuario_tem_permissao, _is_admin_ou_acesso_total
    if _is_admin_ou_acesso_total(request):
        return True
    if usuario_tem_permissao(request, 'acesso_auditoria'):
        return False
    return True


def requer_escrita_financeira(view_func):
    """Decorator: bloqueia acesso de escrita a auditores."""
    def wrapper(request, *args, **kwargs):
        if not _pode_escrever(request):
            messages.error(request, 'OperaÃ§Ã£o nÃ£o permitida. Auditores tÃªm acesso apenas de leitura.')
            referer = request.META.get('HTTP_REFERER')
            if referer:
                return redirect(referer)
            return redirect('financeiro:factura_lista')
        return view_func(request, *args, **kwargs)
    return wrapper
from .forms import (
    FacturaClienteForm, ReciboClienteForm, ReciboClienteUpdateForm,
    NotaCreditoForm, NotaDebitoForm, FacturaReciboForm
)

class BaseContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.session.get('usuario'):
            context['usuario'] = self.request.session['usuario']
            context['papel'] = self.request.session['usuario'].get('papel', '')
            context['nome'] = self.request.session['usuario'].get('nome', '')
        from users.permissoes import get_usuario_permissoes
        context['user_permissoes'] = get_usuario_permissoes(self.request)
        context['pode_aprovar_requisicao'] = _user_tem_acesso_total(self.request) or (
            'aprovar_requisicao' in context['user_permissoes']
        )
        return context

    def _resolve_usuario_id(self):
        """Retorna o usuario_id efectivo para filtragem de dados.
        
        Para colaboradores da banca, usa o usuario_id do despachante dono da banca.
        Para os restantes users, usa o prÃ³prio usuario_id da sessÃ£o.
        """
        banca_usuario_id = self.request.session.get('banca_usuario_id')
        if banca_usuario_id:
            return banca_usuario_id
        return self.request.session.get('usuario_id')

    def _get_user_cliente_filter(self):
        if _user_tem_acesso_total(self.request):
            return {}
        from users.permissoes import get_usuario_permissoes
        perm_set = get_usuario_permissoes(self.request)
        banca_id = self.request.session.get('banca_id')
        if not banca_id:
            usuario_id = self._resolve_usuario_id()
            if not usuario_id:
                return {}
            return {'cliente__usuario_id': usuario_id}
        filtro = {'banca_id': banca_id}
        filial_id = self.request.session.get('colaborador_filial_id')
        if _tem_escopo_filial(perm_set, filial_id) and filial_id:
            filtro['filial_id'] = filial_id
        return filtro

    def _get_user_filter_direct(self):
        if _user_tem_acesso_total(self.request):
            return {}
        from users.permissoes import get_usuario_permissoes
        perm_set = get_usuario_permissoes(self.request)
        banca_id = self.request.session.get('banca_id')
        if not banca_id:
            usuario_id = self._resolve_usuario_id()
            if not usuario_id:
                return {}
            return {'usuario_id': usuario_id}
        filtro = {'banca_id': banca_id}
        filial_id = self.request.session.get('colaborador_filial_id')
        if _tem_escopo_filial(perm_set, filial_id) and filial_id:
            filtro['filial_id'] = filial_id
        return filtro

# â”€â”€â”€ Notas Home â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/notas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas'
        return context


# â”€â”€â”€ Facturas Home â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/facturas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas'
        return context


# â”€â”€â”€ DU â†’ Factura Consolidation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@requer_sessao_ativa
def du_custos_json(request, pk):
    if _user_tem_acesso_total(request):
        du = get_object_or_404(DeclaracaoUnica, pk=pk, status='Aprovada')
    else:
        usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
        du = get_object_or_404(DeclaracaoUnica, pk=pk, status='Aprovada', despachante_id=usuario_id)
    taxas = float(str(du.total_impostos or 0))
    emolumentos = float(str(du.total_emgead or 0))
    iva_val = float(str(du.iva or 0))
    base = taxas + emolumentos
    honorarios = round(base * 0.05, 2)
    despesas = round(base * 0.02, 2)
    total_encargos = base + honorarios + despesas + iva_val
    data = {
        'taxas_aduaneiras': taxas,
        'emolumentos': emolumentos,
        'iva': iva_val,
        'honorarios_despachante': honorarios,
        'despesas_operacionais': despesas,
        'outros_encargos': 0,
        'total_estimado': round(total_encargos, 2),
    }
    return JsonResponse(data)


def _get_object_or_404_com_scope(request, model, pk, scope_field='cliente__usuario_id'):
    base = {'pk': pk}
    banca_id = request.session.get('banca_id')
    if banca_id:
        base['banca_id'] = banca_id
    if _user_tem_acesso_total(request):
        return get_object_or_404(model, **base)
    usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
    if not usuario_id:
        return get_object_or_404(model, **base)
    base[scope_field] = usuario_id
    return get_object_or_404(model, **base)




# â”€â”€â”€ Facturas Finais â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaClienteListView(BaseContextMixin, ListView):
    model = FacturaCliente
    template_name = 'financeiro/factura_lista.html'
    context_object_name = 'facturas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_factura__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_finais'
        return context

# ELIMINADO: Criacão standalone substituída pela criacão a partir da Requisição de Fundo
# @method_decorator(requer_sessao_ativa, name='dispatch')
# @method_decorator(requer_escrita_financeira, name='dispatch')
# class FacturaClienteCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
#     model = FacturaCliente
#     form_class = FacturaClienteForm
#     template_name = 'financeiro/factura_form.html'
#     success_url = reverse_lazy('financeiro:factura_lista')
#     success_message = "Factura Final criada com sucesso!"
# 
#     def form_valid(self, form):
#         form.instance.criado_por_id = self.request.session.get('usuario_id')
#         usuario_data = self.request.session.get('usuario', {})
#         form.instance.criado_por_nome = usuario_data.get('nome', '')
#         form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
#         form.instance.filial_id = self.request.session.get('colaborador_filial_id')
#         response = super().form_valid(form)
#         registrar_historico(
#             'Factura', self.object.pk, self.object.numero_factura, 'Criada',
#             estado_novo=self.object.estado, valor=self.object.valor_total,
#             utilizador_id=self.object.criado_por_id, utilizador_nome=self.object.criado_por_nome,
#             cliente_nome=self.object.cliente.nome,
#             banca_id=self.object.banca_id, filial_id=self.object.filial_id,
#         )
#         return response
# 
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['titulo'] = "Nova Factura Final"
#         context['active_menu'] = 'Financeiro'
#         context['active_sub'] = 'facturas_finais'
#         clientes_qs = Cliente.objects.filter(ativo=True)
#         filtro_cliente = self._get_user_filter_direct()
#         if filtro_cliente:
#             clientes_qs = clientes_qs.filter(**filtro_cliente)
#         context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
#         processos_qs = DeclaracaoUnica.objects.filter(status='Aprovada')
#         context['processos_json'] = json.dumps(list(processos_qs.values('id', 'nif_declarante', 'numero_du')))
#         return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaClienteDetailView(BaseContextMixin, DetailView):
    model = FacturaCliente
    template_name = 'financeiro/factura_detalhe.html'
    context_object_name = 'factura'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'processo_aduaneiro', 'requisicao_fundo')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_finais'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='Factura', documento_id=self.object.pk
        )[:20]
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class FacturaClienteUpdateView(BaseContextMixin, SuccessMessageMixin, UpdateView):
    model = FacturaCliente
    form_class = FacturaClienteForm
    template_name = 'financeiro/factura_form.html'
    success_message = "Factura Final actualizada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:factura_detalhe', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Editar Factura Final"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_finais'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        processos_qs = DeclaracaoUnica.objects.all()
        context['processos_json'] = json.dumps(list(processos_qs.values('id', 'nif_declarante', 'numero_du')))
        return context

    def form_valid(self, form):
        # Não sobrescrever criador em edição
        response = super().form_valid(form)
        registrar_historico(
            'Factura', self.object.pk, self.object.numero_factura, 'Editada',
            estado_novo=self.object.estado, valor=self.object.valor_total,
            utilizador_id=self.request.session.get('usuario_id'),
            utilizador_nome=self.request.session.get('usuario', {}).get('nome', ''),
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response


@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_factura(request, pk):
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    if factura.estado in ('Cancelada', 'Paga'):
        messages.error(request, 'Apenas facturas com estado "Pendente" ou "Parcialmente Paga" podem ser canceladas.')
        return redirect('financeiro:factura_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = factura.estado
        factura.estado = 'Cancelada'
        factura.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Factura', factura.pk, factura.numero_factura, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=factura.valor_total,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=factura.cliente.nome,
            banca_id=factura.banca_id, filial_id=factura.filial_id,
        )
        messages.success(request, f'Factura {factura.numero_factura} cancelada com sucesso.')
    return redirect('financeiro:factura_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
@require_POST
def eliminar_factura(request, pk):
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    
    if factura.recibos.exists():
        messages.error(request, 'Não é possível eliminar uma factura que já possui recibos associados.')
        return redirect('financeiro:factura_detalhe', pk=pk)
    
    numero = factura.numero_factura
    factura.delete()
    messages.success(request, f'Factura {numero} eliminada com sucesso.')
    return redirect('financeiro:factura_lista')


@requer_sessao_ativa
@requer_escrita_financeira
def factura_enviar_email(request, pk):
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    cliente = factura.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} nÃ£o possui endereÃ§o de email configurado.')
        return redirect('financeiro:factura_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        dados_kv_pdf = [
            ('NIF do Cliente', factura.cliente.nif),
            ('Nome do Cliente', factura.cliente.nome),
            ('Processo Aduaneiro', factura.processo_aduaneiro.numero_du if factura.processo_aduaneiro else 'N/D'),
            ('Data de EmissÃ£o', factura.data_emissao.strftime('%d/%m/%Y %H:%M')),
            ('Data de Vencimento', factura.data_vencimento.strftime('%d/%m/%Y')),
            ('Estado', factura.estado),
            ('Emitido Por', factura.criado_por_nome),
            ('DescriÃ§Ã£o', factura.descricao),
        ]
        colunas_pdf = ['DescriÃ§Ã£o do Item / Encargo', 'Valor (KZ)']
        linhas_pdf = [
            ['HonorÃ¡rios do Despachante', fmt_kz(factura.honorarios_despachante)],
            ['Taxas Aduaneiras', fmt_kz(factura.taxas_aduaneiras)],
            ['Emolumentos', fmt_kz(factura.emolumentos)],
            ['Despesas Operacionais', fmt_kz(factura.despesas_operacionais)],
            ['IVA', fmt_kz(factura.iva)],
            ['Outros Encargos', fmt_kz(factura.outros_encargos)],
        ]
        _construir_pdf_base(
            buffer, f"Factura Final {factura.numero_factura}",
            "Documento de CobranÃ§a de Despacho Aduaneiro", factura.estado,
            dados_kv_pdf, colunas_pdf, linhas_pdf, factura.valor_total
        )
        buffer.seek(0)
        anexos = [(f'Factura_{factura.numero_factura}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Factura Final {factura.numero_factura} â€” SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Factura Final referente Ã  prestaÃ§Ã£o de serviÃ§os de despacho.

Detalhes:
  NÃºmero: {factura.numero_factura}
  Valor Total: {fmt_kz(factura.valor_total)} KZ
  Valor Pago: {fmt_kz(factura.valor_pago)} KZ
  Estado: {factura.estado}
  Data de Vencimento: {factura.data_vencimento.strftime('%d/%m/%Y')}

Agradecemos a sua preferÃªncia.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Factura Final</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Factura Final com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">NÃºmero:</td>
                    <td style="padding: 10px;">{factura.numero_factura}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Total:</td>
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{fmt_kz(factura.valor_total)} KZ</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Pago:</td>
                    <td style="padding: 10px;">{fmt_kz(factura.valor_pago)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Estado:</td>
                    <td style="padding: 10px;">{factura.estado}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Vencimento:</td>
                    <td style="padding: 10px;">{factura.data_vencimento.strftime('%d/%m/%Y')}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Processo:</td>
                    <td style="padding: 10px;">{factura.processo_aduaneiro.numero_du if factura.processo_aduaneiro else 'N/D'}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Agradecemos a sua preferÃªncia.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Factura {factura.numero_factura} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:factura_detalhe', pk=pk)


# â”€â”€â”€ GestÃ£o de Recibos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class ReciboClienteListView(BaseContextMixin, ListView):
    model = ReciboCliente
    template_name = 'financeiro/recibo_lista.html'
    context_object_name = 'recibos'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_recibo__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'recibos'
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class ReciboClienteCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = ReciboCliente
    form_class = ReciboClienteForm
    template_name = 'financeiro/recibo_form.html'
    success_url = reverse_lazy('financeiro:recibo_lista')
    success_message = "Recibo emitido com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_responsavel_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_responsavel_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        response = super().form_valid(form)
        registrar_historico(
            'Recibo', self.object.pk, self.object.numero_recibo, 'Criado',
            estado_novo='Pago', valor=self.object.valor_recebido,
            utilizador_id=self.object.utilizador_responsavel_id, utilizador_nome=self.object.utilizador_responsavel_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Novo Recibo de Cliente"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'recibos'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.all()
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total', 'valor_pago')), cls=DjangoJSONEncoder)
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class ReciboClienteDetailView(BaseContextMixin, DetailView):
    model = ReciboCliente
    template_name = 'financeiro/recibo_detalhe.html'
    context_object_name = 'recibo'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'recibos'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='Recibo', documento_id=self.object.pk
        )[:20]
        return context


@requer_sessao_ativa
def cancelar_recibo(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    if recibo.estado == 'Cancelado':
        messages.error(request, 'Este recibo jÃ¡ estÃ¡ cancelado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    pode_cancelar = _user_tem_acesso_total(request)
    if not pode_cancelar:
        messages.error(request, 'NÃ£o tem permissÃ£o para cancelar recibos.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = recibo.estado
        recibo.estado = 'Cancelado'
        recibo.save(update_fields=['estado'])
        
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Recibo', recibo.pk, recibo.numero_recibo, 'Cancelado',
            estado_anterior=estado_anterior or 'Ativo', estado_novo='Cancelado',
            valor=recibo.valor_recebido,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=recibo.cliente.nome,
            banca_id=recibo.banca_id, filial_id=recibo.filial_id,
        )
        messages.success(request, f'Recibo {recibo.numero_recibo} cancelado com sucesso.')
    return redirect('financeiro:recibo_detalhe', pk=pk)


@requer_sessao_ativa
def editar_recibo(request, pk):
    from .forms import ReciboClienteUpdateForm
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    if not recibo.editavel:
        messages.error(request, 'Este recibo nÃ£o pode ser editado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    pode_editar = _user_tem_acesso_total(request)
    if not pode_editar:
        messages.error(request, 'NÃ£o tem permissÃ£o para editar recibos.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    if request.method == 'POST':
        form = ReciboClienteUpdateForm(request.POST, instance=recibo)
        if form.is_valid():
            form.save()
            messages.success(request, f'Recibo {recibo.numero_recibo} atualizado com sucesso.')
            return redirect('financeiro:recibo_detalhe', pk=pk)
    else:
        form = ReciboClienteUpdateForm(instance=recibo)

    context = {
        'form': form,
        'recibo': recibo,
        'titulo': f'Editar Recibo {recibo.numero_recibo}',
        'active_menu': 'Financeiro',
        'active_sub': 'recibos',
    }
    if request.session.get('usuario'):
        context['usuario'] = request.session['usuario']
        context['papel'] = request.session['usuario'].get('papel', '')
        context['nome'] = request.session['usuario'].get('nome', '')
    return render(request, 'financeiro/recibo_form.html', context)


# â”€â”€â”€ Notas de CrÃ©dito â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaCreditoListView(BaseContextMixin, ListView):
    model = NotaCredito
    template_name = 'financeiro/nota_credito_lista.html'
    context_object_name = 'notas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura_relacionada')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_nota__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_credito'
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class NotaCreditoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'financeiro/nota_credito_form.html'
    success_url = reverse_lazy('financeiro:nota_credito_lista')
    success_message = "Nota de CrÃ©dito emitida com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        response = super().form_valid(form)
        registrar_historico(
            'NotaCredito', self.object.pk, self.object.numero_nota, 'Criada',
            estado_novo='Pendente', valor=self.object.valor_creditado,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Nota de CrÃ©dito"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_credito'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.all()
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total')), cls=DjangoJSONEncoder)
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaCreditoDetailView(BaseContextMixin, DetailView):
    model = NotaCredito
    template_name = 'financeiro/nota_credito_detalhe.html'
    context_object_name = 'nota'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura_relacionada')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_credito'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='NotaCredito', documento_id=self.object.pk
        )[:20]
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class NotaCreditoUpdateView(BaseContextMixin, SuccessMessageMixin, UpdateView):
    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'financeiro/nota_credito_form.html'
    success_message = "Nota de CrÃ©dito actualizada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:nota_credito_detalhe', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs.filter(estado='Pendente')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Editar Nota de CrÃ©dito"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_credito'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.all()
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total')), cls=DjangoJSONEncoder)
        return context

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'NotaCredito', self.object.pk, self.object.numero_nota, 'Editada',
            estado_novo=self.object.estado, valor=self.object.valor_creditado,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response


@requer_sessao_ativa
def aprovar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_aprovar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_aprovar:
        messages.error(request, 'NÃ£o tem permissÃ£o para aprovar esta nota de crÃ©dito.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Aprovada'
        nota.utilizador_aprovador_id = usuario_id
        usuario_data = request.session.get('usuario', {})
        nota.utilizador_aprovador_nome = usuario_data.get('nome', '')
        nota.data_aprovacao = timezone.now()
        nota.save()
        registrar_historico(
            'NotaCredito', nota.pk, nota.numero_nota, 'Aprovada',
            estado_anterior=estado_anterior, estado_novo='Aprovada', valor=nota.valor_creditado,
            utilizador_id=nota.utilizador_aprovador_id, utilizador_nome=nota.utilizador_aprovador_nome,
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.success(request, f'Nota de CrÃ©dito {nota.numero_nota} aprovada e creditada na conta corrente do cliente.')

        # Envio automÃ¡tico de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de CrÃ©dito {nota.numero_nota} aprovada â€” SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de CrÃ©dito {nota.numero_nota} foi aprovada no valor de {fmt_kz(nota.valor_creditado)} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                logger.exception("Falha ao enviar email de aprovaÃ§Ã£o de Nota de CrÃ©dito %s", nota.numero_nota)
    return redirect('financeiro:nota_credito_detalhe', pk=pk)

@requer_sessao_ativa
def rejeitar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_rejeitar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_rejeitar:
        messages.error(request, 'NÃ£o tem permissÃ£o para rejeitar esta nota de crÃ©dito.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Rejeitada'
        nota.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'NotaCredito', nota.pk, nota.numero_nota, 'Rejeitada',
            estado_anterior=estado_anterior, estado_novo='Rejeitada', valor=nota.valor_creditado,
            utilizador_id=usuario_id, utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.warning(request, f'Nota de CrÃ©dito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@requer_sessao_ativa
def cancelar_nota_credito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    if nota.estado not in ('Pendente',):
        messages.error(request, 'Apenas notas de crÃ©dito pendentes podem ser canceladas.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_cancelar:
        messages.error(request, 'Apenas o criador ou o Administrador podem cancelar esta nota de crÃ©dito.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Cancelada'
        nota.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'NotaCredito', nota.pk, nota.numero_nota, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=nota.valor_creditado,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.success(request, f'Nota de CrÃ©dito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


# â”€â”€â”€ Notas de DÃ©bito â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaDebitoListView(BaseContextMixin, ListView):
    model = NotaDebito
    template_name = 'financeiro/nota_debito_lista.html'
    context_object_name = 'notas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura_relacionada')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_nota__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_debito'
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class NotaDebitoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'financeiro/nota_debito_form.html'
    success_url = reverse_lazy('financeiro:nota_debito_lista')
    success_message = "Nota de DÃ©bito emitida com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        response = super().form_valid(form)
        registrar_historico(
            'NotaDebito', self.object.pk, self.object.numero_nota, 'Criada',
            estado_novo='Pendente', valor=self.object.valor,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Nota de DÃ©bito"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_debito'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.all()
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total')), cls=DjangoJSONEncoder)
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaDebitoDetailView(BaseContextMixin, DetailView):
    model = NotaDebito
    template_name = 'financeiro/nota_debito_detalhe.html'
    context_object_name = 'nota'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura_relacionada')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_debito'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='NotaDebito', documento_id=self.object.pk
        )[:20]
        return context


@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class NotaDebitoUpdateView(BaseContextMixin, SuccessMessageMixin, UpdateView):
    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'financeiro/nota_debito_form.html'
    success_message = "Nota de DÃ©bito actualizada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:nota_debito_detalhe', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs.filter(estado='Pendente')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Editar Nota de DÃ©bito"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas_debito'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.all()
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total')), cls=DjangoJSONEncoder)
        return context

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'NotaDebito', self.object.pk, self.object.numero_nota, 'Editada',
            estado_novo=self.object.estado, valor=self.object.valor,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response


@requer_sessao_ativa
def aprovar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_aprovar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_aprovar:
        messages.error(request, 'NÃ£o tem permissÃ£o para aprovar esta nota de dÃ©bito.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Aprovada'
        nota.utilizador_aprovador_id = usuario_id
        usuario_data = request.session.get('usuario', {})
        nota.utilizador_aprovador_nome = usuario_data.get('nome', '')
        nota.data_aprovacao = timezone.now()
        nota.save()
        registrar_historico(
            'NotaDebito', nota.pk, nota.numero_nota, 'Aprovada',
            estado_anterior=estado_anterior, estado_novo='Aprovada', valor=nota.valor,
            utilizador_id=nota.utilizador_aprovador_id, utilizador_nome=nota.utilizador_aprovador_nome,
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.success(request, f'Nota de DÃ©bito {nota.numero_nota} aprovada e debitada na conta corrente do cliente.')

        # Envio automÃ¡tico de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de DÃ©bito {nota.numero_nota} aprovada â€” SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de DÃ©bito {nota.numero_nota} foi aprovada no valor de {fmt_kz(nota.valor)} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                logger.exception("Falha ao enviar email de aprovaÃ§Ã£o de Nota de DÃ©bito %s", nota.numero_nota)
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@requer_sessao_ativa
def rejeitar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_rejeitar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_rejeitar:
        messages.error(request, 'NÃ£o tem permissÃ£o para rejeitar esta nota de dÃ©bito.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Rejeitada'
        nota.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'NotaDebito', nota.pk, nota.numero_nota, 'Rejeitada',
            estado_anterior=estado_anterior, estado_novo='Rejeitada', valor=nota.valor,
            utilizador_id=usuario_id, utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.warning(request, f'Nota de DÃ©bito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@requer_sessao_ativa
def cancelar_nota_debito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    if nota.estado not in ('Pendente',):
        messages.error(request, 'Apenas notas de dÃ©bito pendentes podem ser canceladas.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_cancelar:
        messages.error(request, 'Apenas o criador ou o Administrador podem cancelar esta nota de dÃ©bito.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = nota.estado
        nota.estado = 'Cancelada'
        nota.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'NotaDebito', nota.pk, nota.numero_nota, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=nota.valor,
            utilizador_id=usuario_id, utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=nota.cliente.nome,
            banca_id=nota.banca_id, filial_id=nota.filial_id,
        )
        messages.success(request, f'Nota de DÃ©bito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


# â”€â”€â”€ Facturas-Recibo â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaReciboListView(BaseContextMixin, ListView):
    model = FacturaRecibo
    template_name = 'financeiro/factura_recibo_lista.html'
    context_object_name = 'facturas_recibo'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_factura_recibo__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_recibo'
        return context

# ELIMINADO: Criacão standalone substituída pela criacão a partir da Requisição de Fundo
# @method_decorator(requer_sessao_ativa, name='dispatch')
# @method_decorator(requer_escrita_financeira, name='dispatch')
# class FacturaReciboCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
#     model = FacturaRecibo
#     form_class = FacturaReciboForm
#     template_name = 'financeiro/factura_recibo_form.html'
#     success_url = reverse_lazy('financeiro:factura_recibo_lista')
#     success_message = "Factura-Recibo emitida com sucesso!"
# 
#     def form_valid(self, form):
#         form.instance.utilizador_responsavel_id = self.request.session.get('usuario_id')
#         usuario_data = self.request.session.get('usuario', {})
#         form.instance.utilizador_responsavel_nome = usuario_data.get('nome', '')
#         form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
#         form.instance.filial_id = self.request.session.get('colaborador_filial_id')
#         response = super().form_valid(form)
#         registrar_historico(
#             'FacturaRecibo', self.object.pk, self.object.numero_factura_recibo, 'Criada',
#             estado_novo='Paga', valor=self.object.valor,
#             utilizador_id=self.object.utilizador_responsavel_id, utilizador_nome=self.object.utilizador_responsavel_nome,
#             cliente_nome=self.object.cliente.nome,
#             banca_id=self.object.banca_id, filial_id=self.object.filial_id,
#         )
#         return response
# 
#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context['titulo'] = "Nova Factura-Recibo"
#         context['active_menu'] = 'Financeiro'
#         context['active_sub'] = 'facturas_recibo'
#         clientes_qs = Cliente.objects.filter(ativo=True)
#         filtro_cliente = self._get_user_filter_direct()
#         if filtro_cliente:
#             clientes_qs = clientes_qs.filter(**filtro_cliente)
#         context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
#         facturas_qs = FacturaCliente.objects.filter(estado__in=['Pendente', 'Parcialmente Paga'])
#         filtro_factura = self._get_user_cliente_filter()
#         if filtro_factura:
#             facturas_qs = facturas_qs.filter(**filtro_factura)
#         context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total', 'valor_pago')), cls=DjangoJSONEncoder)
#         return context

@method_decorator(requer_sessao_ativa, name='dispatch')
@method_decorator(requer_escrita_financeira, name='dispatch')
class FacturaReciboUpdateView(BaseContextMixin, SuccessMessageMixin, UpdateView):
    model = FacturaRecibo
    form_class = FacturaReciboForm
    template_name = 'financeiro/factura_recibo_form.html'
    success_message = "Factura-Recibo actualizada com sucesso!"

    def get_success_url(self):
        return reverse('financeiro:factura_recibo_detalhe', kwargs={'pk': self.object.pk})

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs.exclude(estado='Cancelada')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Editar Factura-Recibo"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_recibo'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        facturas_qs = FacturaCliente.objects.filter(estado__in=['Pendente', 'Parcialmente Paga'])
        filtro_factura = self._get_user_cliente_filter()
        if filtro_factura:
            facturas_qs = facturas_qs.filter(**filtro_factura)
        context['facturas_json'] = json.dumps(list(facturas_qs.values('id', 'cliente_id', 'numero_factura', 'valor_total', 'valor_pago')), cls=DjangoJSONEncoder)
        return context

    def form_valid(self, form):
        form.instance.utilizador_responsavel_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_responsavel_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'FacturaRecibo', self.object.pk, self.object.numero_factura_recibo, 'Editada',
            estado_novo=self.object.estado, valor=self.object.valor,
            utilizador_id=self.object.utilizador_responsavel_id, utilizador_nome=self.object.utilizador_responsavel_nome,
            cliente_nome=self.object.cliente.nome,
            banca_id=self.object.banca_id, filial_id=self.object.filial_id,
        )
        return response


@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaReciboDetailView(BaseContextMixin, DetailView):
    model = FacturaRecibo
    template_name = 'financeiro/factura_recibo_detalhe.html'
    context_object_name = 'factura_recibo'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'factura')
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_recibo'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='FacturaRecibo', documento_id=self.object.pk
        )[:20]
        return context

@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_factura_recibo(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    if fr.estado != 'Paga':
        messages.error(request, 'Apenas facturas-recibo com estado "Paga" podem ser canceladas.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = fr.estado
        fr.estado = 'Cancelada'
        fr.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'FacturaRecibo', fr.pk, fr.numero_factura_recibo, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=fr.valor,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=fr.cliente.nome,
            banca_id=fr.banca_id, filial_id=fr.filial_id,
        )
        messages.success(request, f'Factura-Recibo {fr.numero_factura_recibo} cancelada com sucesso.')
    return redirect('financeiro:factura_recibo_detalhe', pk=pk)


# â”€â”€â”€ GeraÃ§Ã£o de PDFs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _construir_pdf_base(buffer, titulo, subtitulo, info_geral, dados_kv, tabela_colunas, tabela_linhas, total_geral):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=2*cm,
        title=titulo,
    )
    W = A4[0] - 3.6*cm

    cor_cdoa = colors.HexColor('#1a3a5c')
    cor_cdoa_gold = colors.HexColor('#c9a84c')
    cor_primaria = colors.HexColor('#137fec')
    cor_cabecalho = colors.HexColor('#0f172a')
    cor_borda = colors.HexColor('#e2e8f0')
    cor_label_bg = colors.HexColor('#f1f5f9')
    cor_linha_par = colors.HexColor('#f8fafc')

    s_titulo = ParagraphStyle('titulo', fontSize=18, fontName='Helvetica-Bold', textColor=cor_cabecalho, spaceAfter=2)
    s_subtitulo = ParagraphStyle('subtitulo', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#64748b'))
    s_normal = ParagraphStyle('normal', fontSize=9, fontName='Helvetica', textColor=cor_cabecalho, leading=12)
    s_bold = ParagraphStyle('bold', fontSize=9, fontName='Helvetica-Bold', textColor=cor_cabecalho, leading=12)
    s_small = ParagraphStyle('small', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#64748b'), leading=10)
    s_assinatura = ParagraphStyle('assinatura', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#475569'), leading=11)

    story = []

    # CabeÃ§alho CDOA
    cdoa_header = Table([
        [
            Paragraph('<font color="white"><b>REPÃšBLICA DE ANGOLA</b><br/><font size="8">CÃ‚MARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)</font></font>',
                       ParagraphStyle('cdoa_top', fontSize=11, fontName='Helvetica-Bold', alignment=0, leading=14)),
            Paragraph(f'<font color="{cor_cdoa_gold}"><b>{info_geral}</b></font>',
                       ParagraphStyle('cdoa_right', fontSize=10, fontName='Helvetica-Bold', alignment=2))
        ]
    ], colWidths=[W - 5.5*cm, 5.5*cm])
    cdoa_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_cdoa),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(cdoa_header)
    story.append(Spacer(1, 0.5*cm))

    # TÃ­tulo do documento
    story.append(Paragraph(titulo.upper(), ParagraphStyle('doc_titulo', fontSize=20, fontName='Helvetica-Bold', textColor=cor_cdoa, spaceAfter=4)))
    story.append(Paragraph(subtitulo, s_subtitulo))
    story.append(HRFlowable(width=W, thickness=2, color=cor_cdoa_gold, spaceAfter=12))

    # Tabela KV
    rows = []
    for k, v in dados_kv:
        rows.append([Paragraph(str(k), s_small), Paragraph(str(v) if v else 'N/D', s_normal)])
    t_kv = Table(rows, colWidths=[5.5*cm, W - 5.5*cm])
    t_kv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), cor_label_bg),
        ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, cor_linha_par]),
    ]))
    story.append(t_kv)
    story.append(Spacer(1, 0.6*cm))

    # Tabela de Detalhes
    if tabela_colunas and tabela_linhas:
        story.append(Paragraph("<b>DETALHE DOS CUSTOS / VALORES</b>", ParagraphStyle('det', fontSize=10, fontName='Helvetica-Bold', textColor=cor_primaria, spaceAfter=6)))
        t_data = [tabela_colunas]
        for row in tabela_linhas:
            t_data.append([Paragraph(str(cell), s_normal) for cell in row])
        
        t_det = Table(t_data, colWidths=[W - 4*cm, 4*cm])
        t_det.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        story.append(t_det)
        story.append(Spacer(1, 0.4*cm))

    # Total Geral
    t_tot = Table([[
        Paragraph('<b>TOTAL</b>', ParagraphStyle('tp', fontSize=11, fontName='Helvetica-Bold', textColor=colors.white)),
        Paragraph(f'<b>{fmt_kz(total_geral)} KZ</b>', ParagraphStyle('tv', fontSize=11, fontName='Helvetica-Bold', textColor=colors.white, alignment=2)),
    ]], colWidths=[W - 4*cm, 4*cm])
    t_tot.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_cabecalho),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_tot)

    # Assinatura
    story.append(Spacer(1, 1.2*cm))
    story.append(HRFlowable(width=6.5*cm, thickness=0.8, color=colors.HexColor('#94a3b8'), hAlign='CENTER'))
    story.append(Paragraph('Assinatura do ResponsÃ¡vel', ParagraphStyle('ass', fontSize=8, fontName='Helvetica', alignment=1)))

    doc.build(story)

@requer_sessao_ativa
def factura_pdf(request, pk):
    """Gera PDF da Factura Final no layout oficial angolano (fiel ao modelo FACTURA FT)."""
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    buffer = io.BytesIO()

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from datetime import datetime

    PAGE_W, PAGE_H = A4
    MARGIN = 0.8 * cm
    W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=1.5 * cm,
        title=f"Factura {factura.numero_factura}",
    )

    # ── Cores ─────────────────────────────────────────────────────────────────
    COR_PRETO    = colors.HexColor('#0f172a')
    COR_CINZA    = colors.HexColor('#64748b')
    COR_CLARO    = colors.HexColor('#f1f5f9')
    COR_BORDA    = colors.HexColor('#cbd5e1')
    COR_HEADER   = colors.HexColor('#1e293b')   # cabeçalho da tabela de itens

    # ── Estilos ────────────────────────────────────────────────────────────────
    def st(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRETO, leading=11)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    s_normal   = st('normal')
    s_small    = st('small', fontSize=7, textColor=COR_CINZA, leading=9)
    s_bold     = st('bold', fontName='Helvetica-Bold')
    s_right    = st('right', alignment=TA_RIGHT)
    s_center   = st('center', alignment=TA_CENTER)
    s_th       = st('th', fontName='Helvetica-Bold', fontSize=7, textColor=colors.white, alignment=TA_CENTER, leading=9)
    s_td       = st('td', fontSize=8, leading=10)
    s_td_right = st('td_r', fontSize=8, leading=10, alignment=TA_RIGHT)
    s_td_cent  = st('td_c', fontSize=8, leading=10, alignment=TA_CENTER)

    banca   = factura.banca
    cliente = factura.cliente
    processo = factura.processo_aduaneiro

    story = []

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 1 — Linha superior: paginação + hora + data (direita)
    # ══════════════════════════════════════════════════════════════════════════
    agora = datetime.now()
    top_info = Paragraph(
        f'<font size="7" color="#64748b">Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>',
        st('top_right', alignment=TA_RIGHT, fontSize=7, textColor=COR_CINZA),
    )
    story.append(top_info)
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 2 — Cabeçalho: Logo (esquerda) + Nome/NIF (direita)
    # ══════════════════════════════════════════════════════════════════════════
    logo_path = None
    if banca and hasattr(banca, 'logo') and banca.logo:
        try:
            logo_path = banca.logo.path
        except Exception:
            logo_path = None

    col_logo = []
    if logo_path:
        try:
            col_logo.append(RLImage(logo_path, width=2.8 * cm, height=2.0 * cm))
        except Exception:
            col_logo.append(Paragraph('', s_small))
    else:
        col_logo.append(Paragraph('', s_small))

    nif_txt  = banca.nif if banca else 'N/D'
    nome_txt = banca.nome if banca else 'Despachante Oficial'
    col_nif  = [Paragraph(f'<b>NIF: {nif_txt}</b>', st('nif', fontSize=10, fontName='Helvetica-Bold', alignment=TA_RIGHT))]

    t_logo = Table([[col_logo, col_nif]], colWidths=[W * 0.5, W * 0.5])
    t_logo.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',  (1, 0), (1, 0),  'RIGHT'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_logo)
    story.append(Spacer(1, 0.15 * cm))

    # Nome da empresa em bold grande
    story.append(Paragraph(f'<b>{nome_txt}</b>', st('nome_empresa', fontSize=13, fontName='Helvetica-Bold')))
    story.append(Spacer(1, 0.1 * cm))

    # Endereço + contactos centrados
    endereco  = banca.endereco  if banca else ''
    telefone  = banca.telefone  if banca else ''
    email_b   = banca.email     if banca else ''
    cdoa      = banca.licenca_cdoa if banca else ''
    linha_end = ' | '.join(filter(None, [endereco]))
    linha_tel = ' / '.join(filter(None, [telefone]))
    linha_cdoa = f'Cédula CDOA: {cdoa}' if cdoa else ''

    for linha in filter(None, [linha_end, f'Tel: {linha_tel}' if linha_tel else '', f'E-mail: {email_b}' if email_b else '', linha_cdoa]):
        story.append(Paragraph(f'<font size="8" color="#64748b">{linha}</font>',
                                st('end', fontSize=8, textColor=COR_CINZA, alignment=TA_CENTER)))
    story.append(Spacer(1, 0.25 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 3 — Barra do número da fatura
    # ══════════════════════════════════════════════════════════════════════════
    t_num = Table([[
        Paragraph(f'<b>FACTURA FT {factura.numero_factura}</b>',
                  st('num_ft', fontSize=10, fontName='Helvetica-Bold', textColor=colors.white)),
        Paragraph(f'<font size="9" color="white">Fatura Nº: {factura.numero_factura}</font>',
                  st('num_ft2', fontSize=9, textColor=colors.white, alignment=TA_RIGHT)),
    ]], colWidths=[W * 0.6, W * 0.4])
    t_num.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_HEADER),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_num)
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 4 — Meta-dados (esquerda) + Cliente (direita)
    # ══════════════════════════════════════════════════════════════════════════
    data_emissao   = factura.data_emissao.strftime('%d/%m/%Y')
    data_venc      = factura.data_vencimento.strftime('%d/%m/%Y') if factura.data_vencimento else 'N/D'
    num_interno    = str(factura.pk)
    du_num         = processo.numero_du if processo else 'N/D'
    bl_awb         = ''
    navio_voo      = ''
    data_entrada   = ''
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        rf = factura.requisicao_fundo
        bl_awb    = rf.numero_bl_awb or ''
        navio_voo = rf.meio_transporte or ''
    if processo and hasattr(processo, 'data_submissao') and processo.data_submissao:
        data_entrada = processo.data_submissao.strftime('%d/%m/%Y')

    meta_linhas = [
        ('Data | Date',             data_emissao),
        ('Número Interno | Doc.ID', num_interno),
        ('Desc. Financeiro',        '0,00 %'),
        ('Moeda | Currency',        'AKZ'),
        ('Câmbio | Exch. Rate',     ''),
        ('BL:',                     bl_awb),
        ('Manifesto:',              du_num if du_num != 'N/D' else ''),
        ('Navio / Avião:',          navio_voo),
        ('Data de Entrada:',        data_entrada),
        ('Valor Aduaneiro:',        ''),
        ('Valor CIF:',              fmt_kz(rf.valor_cif) if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo and factura.requisicao_fundo.valor_cif else ''),
    ]

    # Coluna esquerda: meta-dados
    meta_rows = [[Paragraph(f'<font size="7" color="#475569">{k}</font>', s_small),
                  Paragraph(f'<font size="8">{v}</font>', s_td)]
                 for k, v in meta_linhas]

    # Coluna direita: dados cliente
    cli_nome  = cliente.nome if cliente else 'N/D'
    cli_end   = getattr(cliente, 'localizacao', '') or ''
    cli_pais  = 'ANGOLA'
    cli_ref   = ''
    cli_nif   = f'NIF: {cliente.nif}' if cliente else ''

    cliente_block = Paragraph(
        f'<b><font size="11">{cli_nome}</font></b><br/>'
        f'<font size="8">{cli_end}<br/>{cli_pais}<br/>REF:<br/>{cli_nif}</font>',
        st('cli_blk', fontSize=8, leading=12),
    )

    # V/Ref e Tipo de mercadorias
    vref_nome  = ''
    merc_tipo  = ''
    peso_str   = ''
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        rf = factura.requisicao_fundo
        vref_nome = rf.pessoa_contacto or ''
        merc_tipo = rf.mercadoria_descricao or ''
        if rf.peso_bruto_kg:
            peso_str = f'{rf.peso_bruto_kg:.2f}'
    if not merc_tipo and processo and hasattr(processo, 'descricao_mercadoria'):
        merc_tipo = processo.descricao_mercadoria or ''
    if not peso_str and processo and hasattr(processo, 'peso_bruto') and processo.peso_bruto:
        peso_str = f'{processo.peso_bruto:.2f}'

    vref_block = Paragraph(
        f'<font size="7" color="#475569">V/Ref: {vref_nome}</font><br/>'
        f'<font size="7" color="#475569">Tipo de mercadorias: {merc_tipo}</font><br/>'
        f'<font size="7" color="#475569">Peso em Kgs: {peso_str}</font>',
        s_small,
    )

    col_meta  = [Table(meta_rows, colWidths=[3.2 * cm, W * 0.35 - 3.2 * cm])]
    col_cli   = [cliente_block, Spacer(1, 0.3 * cm), vref_block]

    t_meta = Table([[col_meta, col_cli]], colWidths=[W * 0.45, W * 0.55])
    t_meta.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('GRID',          (0, 0), (-1, -1), 0.3, COR_BORDA),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 0.15 * cm))

    # ── Subtítulo "Original"
    story.append(Paragraph('<b>Original</b>', st('orig', fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER)))
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 5 — Tabela de itens (Ref | Item | A | Descrição | Quant.Un | Preço | %Desc | %IVA | Valor)
    # ══════════════════════════════════════════════════════════════════════════
    # Cabeçalho
    ITENS_HEADER = [
        Paragraph('Ref. | Item', s_th),
        Paragraph('A',           s_th),
        Paragraph('Discriminação | Description', s_th),
        Paragraph('Quant. Un',   s_th),
        Paragraph('Preço | Price', s_th),
        Paragraph('%Desc',       s_th),
        Paragraph('%IVA',        s_th),
        Paragraph('Valor | Amount', s_th),
    ]
    # Larguras das colunas
    cw = [1.4*cm, 0.6*cm, W - 1.4*cm - 0.6*cm - 1.8*cm - 2.0*cm - 1.2*cm - 1.2*cm - 2.0*cm,
          1.8*cm, 2.0*cm, 1.2*cm, 1.2*cm, 2.0*cm]

    # Construir linhas de itens a partir da Requisição (classificação correcta)
    ITENS = [ITENS_HEADER]
    DESP_TAXAS = {'Direitos Aduaneiros', 'Taxa Administrativa', 'Inspeção Sanitária',
                   'Multas e Desdobramento', 'Multas', 'Direitos e importações', 'EP 14', 'EP 15', 'EP 17'}
    DESP_EMOL  = {'JUP', 'Factura de Exportação', 'Emissão DAR', 'Emolumentos Gerais AD'}

    taxas_total = Decimal('0')
    emol_total  = Decimal('0')
    oper_total  = Decimal('0')
    honor_total = Decimal('0')
    outros_total = Decimal('0')
    
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        for linha in factura.requisicao_fundo.linhas.all():
            v = linha.valor or Decimal('0')
            if not v or v <= 0:
                continue
            tc = (linha.tipo_custo or '').strip()
            dt = (linha.despesa_tipo or '').strip()
            
            # Classificar pelo tipo de custo primeiro
            if tc == 'Honorários do Despachante' or dt.startswith('Honorário'):
                honor_total += v
            elif tc == 'Impostos e Taxas Aduaneiras (AGT)' or dt in DESP_TAXAS:
                taxas_total += v
            elif tc == 'Despesas Portuárias e Terminais' or dt in DESP_EMOL:
                emol_total += v
            elif tc == 'Logística e Transporte':
                oper_total += v
            else:
                outros_total += v

    # Fallback para Facturas sem requisição vinculada
    if not honor_total and not taxas_total and not emol_total and not oper_total and not outros_total:
        taxas_total = factura.taxas_aduaneiras
        emol_total  = factura.emolumentos
        oper_total  = factura.despesas_operacionais
        honor_total = factura.honorarios_despachante
        outros_total = factura.outros_encargos

    item_map = [
        ('06', 'Impostos e Taxas Aduaneiras', taxas_total),
        ('07', 'Emolumentos Gerais', emol_total),
        ('08', 'Despesas Operacionais', oper_total),
        ('14', 'Honorários do Despachante', honor_total),
    ]

    for ref, desc, valor in item_map:
        if not valor or valor <= 0:
            continue
        if ref == '14':
            pct_iva = '14%'
        else:
            pct_iva = 'M00'
        ITENS.append([
            Paragraph(ref,  s_td_cent),
            Paragraph('1',  s_td_cent),
            Paragraph(desc, s_td),
            Paragraph('1,00 UN', s_td_cent),
            Paragraph(fmt_kz(valor), s_td_cent),
            Paragraph('—', s_td_cent),
            Paragraph(pct_iva, s_td_cent),
            Paragraph(fmt_kz(valor), s_td_right),
        ])

    # Linhas em branco para preencher o espaço (mínimo 8 linhas de itens)
    while len(ITENS) < 10:
        ITENS.append(['', '', '', '', '', '', '', ''])

    t_itens = Table(ITENS, colWidths=cw, repeatRows=1)
    t_itens.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND',    (0, 0), (-1, 0), COR_HEADER),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 7),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, 0), 5),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
        # Corpo
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, COR_BORDA),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, COR_CLARO]),
        ('VALIGN',        (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
    ]))
    story.append(t_itens)
    story.append(Spacer(1, 0.15 * cm))

    # ── Nota de bens
    story.append(Paragraph(
        '<font size="7" color="#475569"><i>Bens foram colocados à disposição do adquirente a data do documento</i></font>',
        s_small,
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 6 — Resumo IVA (esquerda) + Totalizadores (direita)
    # ══════════════════════════════════════════════════════════════════════════
    # Resumo IVA
    iva_rows = [
        [Paragraph('<b>Resumo IVA</b>', st('iva_t', fontSize=8, fontName='Helvetica-Bold')),'','',''],
        [Paragraph('<b>Cód. IVA</b>', s_th), Paragraph('<b>Incidência</b>', s_th),
         Paragraph('<b>%IVA</b>', s_th), Paragraph('<b>Valor Motivo</b>', s_th)],
        ['14%',
         Paragraph(fmt_kz(factura.honorarios_despachante), s_td_right),
         Paragraph('14,00', s_td_right),
         Paragraph(f'{fmt_kz(factura.iva)} IVA - Regime Simplificado', s_td)],
        ['', Paragraph('<b>0,00</b>', s_td_right), Paragraph('<b>0,00</b>', s_td_right), ''],
    ]
    t_iva = Table(iva_rows, colWidths=[1.4*cm, 2.0*cm, 1.2*cm, W*0.35 - 4.6*cm])
    t_iva.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 1), (-1, 1), COR_HEADER),
        ('TEXTCOLOR',     (0, 1), (-1, 1), colors.white),
        ('GRID',          (0, 1), (-1, -1), 0.3, COR_BORDA),
        ('BOX',           (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica'),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('ALIGN',         (0, 2), (2, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Totalizadores direita
    def _tot_row(label, valor, bold=False, big=False):
        fn = 'Helvetica-Bold' if bold else 'Helvetica'
        fs = 10 if big else 8
        return [
            Paragraph(f'<font size="{fs}" name="{fn}">{label}</font>',
                       st(f'tot_{label}', fontSize=fs, fontName=fn, alignment=TA_LEFT)),
            Paragraph(f'<font size="{fs}" name="{fn}">{valor}</font>',
                       st(f'totv_{label}', fontSize=fs, fontName=fn, alignment=TA_RIGHT)),
        ]

    retencao_valor = Decimal('0')
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        retencao_valor = factura.requisicao_fundo.retencao or Decimal('0')

    tot_rows = [
        _tot_row('Mercadorias',  fmt_kz(taxas_total + emol_total + oper_total + outros_total)),
        _tot_row('Serviços',     fmt_kz(honor_total)),
        _tot_row('Outros',       fmt_kz(factura.outros_encargos)),
        _tot_row('IEC',          '0,00'),
        _tot_row('Retenção',     fmt_kz(retencao_valor) if retencao_valor > 0 else '0,00'),
        _tot_row('Descontos',    '0,00'),
        _tot_row('Total IVA',    fmt_kz(factura.iva)),
        _tot_row(f'Total (AKZ):', fmt_kz(factura.valor_total), bold=True, big=True),
        [Paragraph(''), Paragraph('')],
        _tot_row('Total Alternativo:', fmt_kz(factura.valor_total)),
    ]

    t_tot = Table(tot_rows, colWidths=[W * 0.35, W * 0.2])
    t_tot.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -2), 0.3, COR_BORDA),
        ('LINEABOVE',     (0, 7), (-1, 7), 1.0, COR_PRETO),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Montar os dois em paralelo
    spacer_col = [[Spacer(1, 0.1*cm)]]
    t_bottom = Table(
        [[t_iva, '', t_tot]],
        colWidths=[W * 0.42, W * 0.03, W * 0.55],
    )
    t_bottom.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',  (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_bottom)
    story.append(Spacer(1, 0.5 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 7 — Assinatura + Operador
    # ══════════════════════════════════════════════════════════════════════════
    t_ass = Table([[
        '',
        Table([[HRFlowable(width=4*cm, thickness=0.5, color=COR_BORDA)],
               [Paragraph('<font size="8">Assinatura</font>',
                           st('ass', fontSize=8, alignment=TA_CENTER))],
               [Spacer(1, 0.3*cm)],
               [HRFlowable(width=4*cm, thickness=0.5, color=COR_BORDA)],
               [Paragraph(f'<font size="8">Operador: {factura.criado_por_nome or "—"}</font>',
                           st('op', fontSize=8, alignment=TA_CENTER))],
               ], colWidths=[4*cm]),
    ]], colWidths=[W - 4*cm, 4*cm])
    t_ass.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN',  (1, 0), (1, 0),  'CENTER'),
    ]))
    story.append(t_ass)

    # ══════════════════════════════════════════════════════════════════════════
    # CONSTRUIR E RETORNAR
    # ══════════════════════════════════════════════════════════════════════════
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Factura_{factura.numero_factura}.pdf"'
    return response

@requer_sessao_ativa
def recibo_pdf(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    buffer = io.BytesIO()

    dados_kv = [
        ('NIF do Cliente', recibo.cliente.nif),
        ('Nome do Cliente', recibo.cliente.nome),
        ('Factura Relacionada', recibo.factura.numero_factura),
        ('Forma de Pagamento', recibo.forma_pagamento),
        ('Data do Pagamento', recibo.data_pagamento.strftime('%d/%m/%Y')),
        ('Referência Bancária', recibo.referencia_bancaria or 'N/D'),
        ('Emitido Por', recibo.utilizador_responsavel_nome),
        ('Estado', 'PAGO'),
    ]

    colunas = ['Conceito', 'Valor Recebido (KZ)']
    linhas = [
        [f'Pagamento da Factura {recibo.factura.numero_factura}', fmt_kz(recibo.valor_recebido)]
    ]

    _construir_pdf_base(
        buffer, 
        f"Recibo de Pagamento {recibo.numero_recibo}",
        f"Documento Comprovativo de Pagamento",
        "PAGO",
        dados_kv,
        colunas,
        linhas,
        recibo.valor_recebido
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Recibo_{recibo.numero_recibo}.pdf"'
    return response

@requer_sessao_ativa

def nota_credito_pdf(request, pk):

    """Gera PDF da Nota de CrÃ©dito com design profissional"""

    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)

    buffer = io.BytesIO()

    

    from reportlab.lib import colors

    from reportlab.lib.pagesizes import A4

    from reportlab.lib.styles import ParagraphStyle

    from reportlab.lib.units import cm

    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage

    from reportlab.platypus.flowables import HRFlowable

    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    

    doc = SimpleDocTemplate(

        buffer, pagesize=A4,

        leftMargin=0.8*cm, rightMargin=0.8*cm,

        topMargin=0.8*cm, bottomMargin=1.5*cm,

        title=f"Nota de CrÃ©dito {nota.numero_nota}",

    )

    W = A4[0] - 1.6*cm

    

    cor_cabecalho = colors.HexColor('#0f172a')

    cor_credito = colors.HexColor('#10b981')

    cor_cinza_claro = colors.HexColor('#f1f5f9')

    cor_borda = colors.HexColor('#cbd5e1')

    

    s_small = ParagraphStyle('small', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#64748b'), leading=10)

    

    story = []

    

    banca = nota.banca

    logo_path = None

    if banca and hasattr(banca, 'logo') and banca.logo:

        logo_path = banca.logo.path

    

    col1 = []

    if logo_path:

        try:

            img = RLImage(logo_path, width=2.2*cm, height=1.5*cm)

            col1.append(img)

        except:

            col1.append(Paragraph('<i>Logo nÃ£o encontrado</i>', s_small))

    else:

        col1.append(Paragraph('', s_small))

    

    col2_text = f"""<b>{banca.nome if banca else 'Banca'}</b><br/>

<font size="7">NIF: {banca.nif if banca and hasattr(banca, 'nif') else 'N/D'}<br/>

{banca.endereco if banca and hasattr(banca, 'endereco') else ''}<br/>

Tel: {banca.telefone if banca and hasattr(banca, 'telefone') else 'N/D'}</font>"""

    col2 = [Paragraph(col2_text, ParagraphStyle('banca_info', fontSize=10, fontName='Helvetica', textColor=cor_cabecalho, leading=12))]

    

    col3_text = f"""<b>NOTA DE CRÃ‰DITO</b><br/>

<font size="8" color="#10b981"><b>NÂº: {nota.numero_nota}</b></font><br/>

<font size="8">Data: {nota.data.strftime('%d/%m/%Y')}<br/>

Estado: {nota.estado}</font>"""

    col3 = [Paragraph(col3_text, ParagraphStyle('doc_info', fontSize=10, fontName='Helvetica-Bold', textColor=cor_credito, leading=12, alignment=TA_RIGHT))]

    

    t_cabecalho = Table([[col1, col2, col3]], colWidths=[2.5*cm, W/2 - 1.25*cm, W/2 - 1.25*cm])

    t_cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (2, 0), (2, 0), 'RIGHT')]))

    story.append(t_cabecalho)

    story.append(Spacer(1, 0.3*cm))

    story.append(HRFlowable(width=W, thickness=1.5, color=cor_credito))

    story.append(Spacer(1, 0.3*cm))

    

    cliente = nota.cliente

    factura = nota.factura_relacionada

    

    cliente_text = f"""<b>CLIENTE</b><br/>

<font size="8">{cliente.nome}<br/>

NIF: {cliente.nif}<br/>

Telefone: {cliente.telefone or 'N/D'}<br/>

Email: {cliente.email or 'N/D'}</font>"""

    

    doc_text = f"""<b>DOCUMENTO RELACIONADO</b><br/>

<font size="8">Factura: {factura.numero_factura if factura else 'N/D'}<br/>

Data Factura: {factura.data.strftime('%d/%m/%Y') if factura and hasattr(factura, 'data') else 'N/D'}<br/>

Motivo: {nota.motivo}<br/>

Estado: <b>{nota.estado}</b></font>"""

    

    t_info = Table([[

        Paragraph(cliente_text, ParagraphStyle('cliente', fontSize=9, fontName='Helvetica', textColor=cor_cabecalho, leading=11)),

        Paragraph(doc_text, ParagraphStyle('doc', fontSize=9, fontName='Helvetica', textColor=cor_cabecalho, leading=11))

    ]], colWidths=[W/2 - 0.2*cm, W/2 - 0.2*cm])

    t_info.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, -1), cor_cinza_claro),

        ('GRID', (0, 0), (-1, -1), 0.5, cor_borda),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

        ('TOPPADDING', (0, 0), (-1, -1), 8),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

        ('VALIGN', (0, 0), (-1, -1), 'TOP'),

    ]))

    story.append(t_info)

    story.append(Spacer(1, 0.5*cm))

    

    story.append(Paragraph('<b style="color:#10b981">DETALHES DA NOTA DE CRÃ‰DITO</b>', ParagraphStyle('tab_titulo', fontSize=10, fontName='Helvetica-Bold', spaceAfter=6)))

    

    linhas_credito = [

        ['Conceito', 'Valor (KZ)'],

        [f'CrÃ©dito referente Ã  Factura {factura.numero_factura if factura else ""}', fmt_kz(nota.valor_creditado or 0)]

    ]

    

    t_credito = Table(linhas_credito, colWidths=[W - 3*cm, 3*cm])

    t_credito.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, 0), cor_credito),

        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, 0), 9),

        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

        ('TOPPADDING', (0, 0), (-1, 0), 6),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),

        ('BACKGROUND', (0, 1), (-1, -1), colors.white),

        ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),

        ('FONTSIZE', (0, 1), (-1, -1), 9),

        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),

        ('TOPPADDING', (0, 0), (-1, -1), 6),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

    ]))

    story.append(t_credito)

    story.append(Spacer(1, 0.4*cm))

    

    t_total = Table([['VALOR TOTAL DO CRÃ‰DITO', fmt_kz(nota.valor_creditado or 0)]], colWidths=[W - 3*cm, 3*cm])

    t_total.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, -1), cor_credito),

        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),

        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, -1), 12),

        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),

        ('TOPPADDING', (0, 0), (-1, -1), 8),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

    ]))

    story.append(t_total)

    story.append(Spacer(1, 0.6*cm))

    

    info_text = f"""<b>InformaÃ§Ãµes de Processamento</b><br/>

<font size="8">Criado por: {nota.utilizador_criador_nome or 'Sistema'} em {nota.data_criacao.strftime('%d/%m/%Y Ã s %H:%M')}<br/>

Aprovado por: {nota.utilizador_aprovador_nome or 'Pendente aprovaÃ§Ã£o'}</font>"""

    story.append(Paragraph(info_text, s_small))

    story.append(Spacer(1, 0.4*cm))

    

    story.append(Spacer(1, 0.5*cm))

    story.append(HRFlowable(width=4*cm, thickness=0.5, color=colors.HexColor('#94a3b8'), hAlign='CENTER'))

    story.append(Paragraph('Assinatura do ResponsÃ¡vel', ParagraphStyle('ass', fontSize=7, fontName='Helvetica', alignment=TA_CENTER)))

    

    story.append(Spacer(1, 0.5*cm))

    rodape_text = f"""<font size="7" color="#64748b">

Esta Nota de CrÃ©dito foi processada por computador. Tem validade legal conforme legislaÃ§Ã£o em vigor.

Emitido em: {nota.data.strftime('%d de %B de %Y')}

    </font>"""

    story.append(Paragraph(rodape_text, ParagraphStyle('rodape', fontSize=7, fontName='Helvetica', textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)))

    

    doc.build(story)

    

    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')

    response['Content-Disposition'] = f'inline; filename="NotaCredito_{nota.numero_nota}.pdf"'

    return response





@requer_sessao_ativa

def nota_debito_pdf(request, pk):

    """Gera PDF da Nota de DÃ©bito com design profissional"""

    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)

    buffer = io.BytesIO()



    from reportlab.lib import colors

    from reportlab.lib.pagesizes import A4

    from reportlab.lib.styles import ParagraphStyle

    from reportlab.lib.units import cm

    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image as RLImage

    from reportlab.platypus.flowables import HRFlowable

    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    

    doc = SimpleDocTemplate(

        buffer, pagesize=A4,

        leftMargin=0.8*cm, rightMargin=0.8*cm,

        topMargin=0.8*cm, bottomMargin=1.5*cm,

        title=f"Nota de DÃ©bito {nota.numero_nota}",

    )

    W = A4[0] - 1.6*cm

    

    cor_cabecalho = colors.HexColor('#0f172a')

    cor_debito = colors.HexColor('#ef4444')

    cor_cinza_claro = colors.HexColor('#f1f5f9')

    cor_borda = colors.HexColor('#cbd5e1')

    

    s_small = ParagraphStyle('small', fontSize=8, fontName='Helvetica', textColor=colors.HexColor('#64748b'), leading=10)

    

    story = []

    

    banca = nota.banca

    logo_path = None

    if banca and hasattr(banca, 'logo') and banca.logo:

        logo_path = banca.logo.path

    

    col1 = []

    if logo_path:

        try:

            img = RLImage(logo_path, width=2.2*cm, height=1.5*cm)

            col1.append(img)

        except:

            col1.append(Paragraph('<i>Logo nÃ£o encontrado</i>', s_small))

    else:

        col1.append(Paragraph('', s_small))

    

    col2_text = f"""<b>{banca.nome if banca else 'Banca'}</b><br/>

<font size="7">NIF: {banca.nif if banca and hasattr(banca, 'nif') else 'N/D'}<br/>

{banca.endereco if banca and hasattr(banca, 'endereco') else ''}<br/>

Tel: {banca.telefone if banca and hasattr(banca, 'telefone') else 'N/D'}</font>"""

    col2 = [Paragraph(col2_text, ParagraphStyle('banca_info', fontSize=10, fontName='Helvetica', textColor=cor_cabecalho, leading=12))]

    

    col3_text = f"""<b>NOTA DE DÃ‰BITO</b><br/>

<font size="8" color="#ef4444"><b>NÂº: {nota.numero_nota}</b></font><br/>

<font size="8">Data: {nota.data.strftime('%d/%m/%Y')}<br/>

Estado: {nota.estado}</font>"""

    col3 = [Paragraph(col3_text, ParagraphStyle('doc_info', fontSize=10, fontName='Helvetica-Bold', textColor=cor_debito, leading=12, alignment=TA_RIGHT))]

    

    t_cabecalho = Table([[col1, col2, col3]], colWidths=[2.5*cm, W/2 - 1.25*cm, W/2 - 1.25*cm])

    t_cabecalho.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('ALIGN', (2, 0), (2, 0), 'RIGHT')]))

    story.append(t_cabecalho)

    story.append(Spacer(1, 0.3*cm))

    story.append(HRFlowable(width=W, thickness=1.5, color=cor_debito))

    story.append(Spacer(1, 0.3*cm))

    

    cliente = nota.cliente

    factura = nota.factura_relacionada

    

    cliente_text = f"""<b>CLIENTE</b><br/>

<font size="8">{cliente.nome}<br/>

NIF: {cliente.nif}<br/>

Telefone: {cliente.telefone or 'N/D'}<br/>

Email: {cliente.email or 'N/D'}</font>"""

    

    doc_text = f"""<b>DOCUMENTO RELACIONADO</b><br/>

<font size="8">Factura: {factura.numero_factura if factura else 'N/D'}<br/>

Data Factura: {factura.data.strftime('%d/%m/%Y') if factura and hasattr(factura, 'data') else 'N/D'}<br/>

Motivo: {nota.motivo}<br/>

Estado: <b>{nota.estado}</b></font>"""

    

    t_info = Table([[

        Paragraph(cliente_text, ParagraphStyle('cliente', fontSize=9, fontName='Helvetica', textColor=cor_cabecalho, leading=11)),

        Paragraph(doc_text, ParagraphStyle('doc', fontSize=9, fontName='Helvetica', textColor=cor_cabecalho, leading=11))

    ]], colWidths=[W/2 - 0.2*cm, W/2 - 0.2*cm])

    t_info.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, -1), cor_cinza_claro),

        ('GRID', (0, 0), (-1, -1), 0.5, cor_borda),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

        ('TOPPADDING', (0, 0), (-1, -1), 8),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

        ('VALIGN', (0, 0), (-1, -1), 'TOP'),

    ]))

    story.append(t_info)

    story.append(Spacer(1, 0.5*cm))

    

    story.append(Paragraph('<b style="color:#ef4444">DETALHES DA NOTA DE DÃ‰BITO</b>', ParagraphStyle('tab_titulo', fontSize=10, fontName='Helvetica-Bold', spaceAfter=6)))

    

    linhas_debito = [

        ['Conceito', 'Valor (KZ)'],

        [f'DÃ©bito adicional referente Ã  Factura {factura.numero_factura if factura else ""}', fmt_kz(nota.valor or 0)]

    ]

    

    t_debito = Table(linhas_debito, colWidths=[W - 3*cm, 3*cm])

    t_debito.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, 0), cor_debito),

        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),

        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, 0), 9),

        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

        ('TOPPADDING', (0, 0), (-1, 0), 6),

        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),

        ('BACKGROUND', (0, 1), (-1, -1), colors.white),

        ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),

        ('FONTSIZE', (0, 1), (-1, -1), 9),

        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),

        ('TOPPADDING', (0, 0), (-1, -1), 6),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

    ]))

    story.append(t_debito)

    story.append(Spacer(1, 0.4*cm))

    

    t_total = Table([['VALOR TOTAL DO DÃ‰BITO', fmt_kz(nota.valor or 0)]], colWidths=[W - 3*cm, 3*cm])

    t_total.setStyle(TableStyle([

        ('BACKGROUND', (0, 0), (-1, -1), cor_debito),

        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),

        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),

        ('FONTSIZE', (0, 0), (-1, -1), 12),

        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),

        ('TOPPADDING', (0, 0), (-1, -1), 8),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),

        ('LEFTPADDING', (0, 0), (-1, -1), 8),

        ('RIGHTPADDING', (0, 0), (-1, -1), 8),

    ]))

    story.append(t_total)

    story.append(Spacer(1, 0.6*cm))

    

    info_text = f"""<b>InformaÃ§Ãµes de Processamento</b><br/>

<font size="8">Criado por: {nota.utilizador_criador_nome or 'Sistema'} em {nota.data_criacao.strftime('%d/%m/%Y Ã s %H:%M')}<br/>

Aprovado por: {nota.utilizador_aprovador_nome or 'Pendente aprovaÃ§Ã£o'}</font>"""

    story.append(Paragraph(info_text, s_small))

    story.append(Spacer(1, 0.4*cm))

    

    story.append(Spacer(1, 0.5*cm))

    story.append(HRFlowable(width=4*cm, thickness=0.5, color=colors.HexColor('#94a3b8'), hAlign='CENTER'))

    story.append(Paragraph('Assinatura do ResponsÃ¡vel', ParagraphStyle('ass', fontSize=7, fontName='Helvetica', alignment=TA_CENTER)))

    

    story.append(Spacer(1, 0.5*cm))

    rodape_text = f"""<font size="7" color="#64748b">

Esta Nota de DÃ©bito foi processada por computador. Tem validade legal conforme legislaÃ§Ã£o em vigor.

Emitido em: {nota.data.strftime('%d de %B de %Y')}

    </font>"""

    story.append(Paragraph(rodape_text, ParagraphStyle('rodape', fontSize=7, fontName='Helvetica', textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER)))

    

    doc.build(story)



    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')

    response['Content-Disposition'] = f'inline; filename="NotaDebito_{nota.numero_nota}.pdf"'

    return response


@requer_sessao_ativa
def factura_recibo_pdf(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    buffer = io.BytesIO()

    dados_kv = [
        ('NIF do Cliente', fr.cliente.nif),
        ('Nome do Cliente', fr.cliente.nome),
        ('Forma de Pagamento', fr.forma_pagamento),
        ('Data do Pagamento', fr.data.strftime('%d/%m/%Y')),
        ('Emitido Por', fr.utilizador_responsavel_nome),
        ('Estado', fr.estado),
    ]

    # Breakdown de custos se houver requisição associada
    requisicao = fr.requisicao_fundo or (fr.factura.requisicao_fundo if fr.factura_id else None)
    if requisicao:
        colunas = ['Rubrica', 'Valor (KZ)']
        linhas = []
        for linha in requisicao.linhas.all():
            if linha.valor:
                desc = linha.despesa_tipo or linha.tipo_custo or 'Outros'
                linhas.append([desc, fmt_kz(linha.valor)])
        if not linhas:
            linhas = [['Honorários do Despachante (Pacote)', fmt_kz(fr.valor)]]
    else:
        colunas = ['Descrição / Venda Direta', 'Valor Pago (KZ)']
        linhas = [
            ['Prestação de Serviços de Despacho com pagamento imediato', fmt_kz(fr.valor)]
        ]

    _construir_pdf_base(
        buffer, 
        f"Factura-Recibo {fr.numero_factura_recibo}",
        f"Venda a Pronto Pagamento",
        "PAGO",
        dados_kv,
        colunas,
        linhas,
        fr.valor
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="FacturaRecibo_{fr.numero_factura_recibo}.pdf"'
    return response


@requer_sessao_ativa
def nota_credito_pdf(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    buffer = io.BytesIO()

    dados_kv = [
        ('NIF do Cliente', nota.cliente.nif),
        ('Nome do Cliente', nota.cliente.nome),
        ('Factura Relacionada', nota.factura_relacionada.numero_factura),
        ('Motivo do Crédito', nota.motivo),
        ('Data de Emissão', nota.data.strftime('%d/%m/%Y')),
        ('Estado', nota.estado),
        ('Criado Por', nota.utilizador_criador_nome),
        ('Aprovado Por', nota.utilizador_aprovador_nome or 'N/D'),
    ]

    colunas = ['Conceito', 'Valor Creditado (KZ)']
    linhas = [
        [f'Crédito referente à Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor_creditado)]
    ]

    _construir_pdf_base(
        buffer, 
        f"Nota de Crédito {nota.numero_nota}",
        "Documento de Retificação de Facturação",
        nota.estado,
        dados_kv,
        colunas,
        linhas,
        nota.valor_creditado
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NotaCredito_{nota.numero_nota}.pdf"'
    return response


@requer_sessao_ativa
def nota_debito_pdf(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    buffer = io.BytesIO()

    dados_kv = [
        ('NIF do Cliente', nota.cliente.nif),
        ('Nome do Cliente', nota.cliente.nome),
        ('Factura Relacionada', nota.factura_relacionada.numero_factura),
        ('Motivo do Débito', nota.motivo),
        ('Data de Emissão', nota.data.strftime('%d/%m/%Y')),
        ('Estado', nota.estado),
        ('Criado Por', nota.utilizador_criador_nome),
    ]

    colunas = ['Conceito', 'Valor Debitado (KZ)']
    linhas = [
        [f'Débito adicional referente à Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor)]
    ]

    _construir_pdf_base(
        buffer, 
        f"Nota de Débito {nota.numero_nota}",
        "Documento de Encargo Adicional",
        nota.estado,
        dados_kv,
        colunas,
        linhas,
        nota.valor
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NotaDebito_{nota.numero_nota}.pdf"'
    return response


# â”€â”€â”€ Envio por Email â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@requer_sessao_ativa
@requer_escrita_financeira
def recibo_enviar_email(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    cliente = recibo.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} nÃ£o possui endereÃ§o de email configurado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        dados_kv = [
            ('NIF do Cliente', recibo.cliente.nif),
            ('Nome do Cliente', recibo.cliente.nome),
            ('Factura Relacionada', recibo.factura.numero_factura),
            ('Forma de Pagamento', recibo.forma_pagamento),
            ('Data do Pagamento', recibo.data_pagamento.strftime('%d/%m/%Y')),
            ('ReferÃªncia BancÃ¡ria', recibo.referencia_bancaria or 'N/D'),
            ('Emitido Por', recibo.utilizador_responsavel_nome),
        ]
        colunas = ['Conceito', 'Valor Recebido (KZ)']
        linhas = [[f'Pagamento da Factura {recibo.factura.numero_factura}', fmt_kz(recibo.valor_recebido)]]
        _construir_pdf_base(
            buffer, f"Recibo de Pagamento {recibo.numero_recibo}",
            "Documento Comprovativo de Pagamento", "PAGO",
            dados_kv, colunas, linhas, recibo.valor_recebido
        )
        buffer.seek(0)
        anexos = [(f'Recibo_{recibo.numero_recibo}.pdf', buffer.read(), 'application/pdf')]
        
        assunto = f"Recibo de Pagamento {recibo.numero_recibo} â€” SICDOA"
        
        texto = f"""Prezado(a) {cliente.nome},
        
Confirmamos a recepÃ§Ã£o do seu pagamento no valor de {fmt_kz(recibo.valor_recebido)} KZ.

Detalhes do Recibo:
  NÃºmero: {recibo.numero_recibo}
  Factura: {recibo.factura.numero_factura}
  Forma de Pagamento: {recibo.forma_pagamento}
  Data do Pagamento: {recibo.data_pagamento.strftime('%d/%m/%Y')}
  ReferÃªncia: {recibo.referencia_bancaria or 'N/D'}

Agradecemos a sua preferÃªncia.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">ConfirmaÃ§Ã£o de Pagamento</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Confirmamos a recepÃ§Ã£o do seu pagamento com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">NÃºmero do Recibo:</td>
                    <td style="padding: 10px;">{recibo.numero_recibo}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Factura:</td>
                    <td style="padding: 10px;">{recibo.factura.numero_factura}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Recebido:</td>
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{fmt_kz(recibo.valor_recebido)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Forma de Pagamento:</td>
                    <td style="padding: 10px;">{recibo.forma_pagamento}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data do Pagamento:</td>
                    <td style="padding: 10px;">{recibo.data_pagamento.strftime('%d/%m/%Y')}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">ReferÃªncia BancÃ¡ria:</td>
                    <td style="padding: 10px;">{recibo.referencia_bancaria or 'N/D'}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Agradecemos a sua preferÃªncia.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Recibo {recibo.numero_recibo} enviado por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:recibo_detalhe', pk=pk)

@requer_sessao_ativa
@requer_escrita_financeira
def factura_recibo_enviar_email(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    cliente = fr.cliente

    if fr.estado == 'Cancelada':
        messages.error(request, 'Não é possível enviar email de uma Factura-Recibo cancelada.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} nÃ£o possui endereÃ§o de email configurado.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        dados_kv_pdf = [
            ('NIF do Cliente', fr.cliente.nif),
            ('Nome do Cliente', fr.cliente.nome),
            ('Forma de Pagamento', fr.forma_pagamento),
            ('Data do Pagamento', fr.data.strftime('%d/%m/%Y')),
            ('Emitido Por', fr.utilizador_responsavel_nome),
            ('Estado', fr.estado),
        ]
        requisicao = fr.requisicao_fundo or (fr.factura.requisicao_fundo if fr.factura_id else None)
        if requisicao:
            colunas_pdf = ['Rubrica', 'Valor (KZ)']
            linhas_pdf = []
            for linha in requisicao.linhas.all():
                if linha.valor:
                    desc = linha.despesa_tipo or linha.tipo_custo or 'Outros'
                    linhas_pdf.append([desc, fmt_kz(linha.valor)])
            if not linhas_pdf:
                linhas_pdf = [['HonorÃ¡rios do Despachante (Pacote)', fmt_kz(fr.valor)]]
        else:
            colunas_pdf = ['DescriÃ§Ã£o / Venda Direta', 'Valor Pago (KZ)']
            linhas_pdf = [
                ['PrestaÃ§Ã£o de ServiÃ§os de Despacho com pagamento imediato', fmt_kz(fr.valor)]
            ]
        _construir_pdf_base(
            buffer, f"Factura-Recibo {fr.numero_factura_recibo}",
            "Venda a Pronto Pagamento", "PAGO",
            dados_kv_pdf, colunas_pdf, linhas_pdf, fr.valor
        )
        buffer.seek(0)
        anexos = [(f'FacturaRecibo_{fr.numero_factura_recibo}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Factura-Recibo {fr.numero_factura_recibo} â€” SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Factura-Recibo referente Ã  prestaÃ§Ã£o de serviÃ§os de despacho.

Detalhes:
  NÃºmero: {fr.numero_factura_recibo}
  Valor: {fmt_kz(fr.valor)} KZ
  Forma de Pagamento: {fr.forma_pagamento}
  Data: {fr.data.strftime('%d/%m/%Y')}

Agradecemos a sua preferÃªncia.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Factura-Recibo â€” ConfirmaÃ§Ã£o de Pagamento</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Factura-Recibo com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">NÃºmero:</td>
                    <td style="padding: 10px;">{fr.numero_factura_recibo}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Pago:</td>
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{fmt_kz(fr.valor)} KZ</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Forma de Pagamento:</td>
                    <td style="padding: 10px;">{fr.forma_pagamento}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data:</td>
                    <td style="padding: 10px;">{fr.data.strftime('%d/%m/%Y')}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Agradecemos a sua preferÃªncia.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Factura-Recibo {fr.numero_factura_recibo} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:factura_recibo_detalhe', pk=pk)


# â”€â”€â”€ Envio por Email â€” Notas de CrÃ©dito e DÃ©bito â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@requer_sessao_ativa
@requer_escrita_financeira
def nota_credito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} nÃ£o possui endereÃ§o de email configurado.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        dados_kv_pdf = [
            ('NIF do Cliente', nota.cliente.nif),
            ('Nome do Cliente', nota.cliente.nome),
            ('Factura Relacionada', nota.factura_relacionada.numero_factura),
            ('Motivo do CrÃ©dito', nota.motivo),
            ('Data de EmissÃ£o', nota.data.strftime('%d/%m/%Y')),
            ('Estado', nota.estado),
            ('Criado Por', nota.utilizador_criador_nome),
            ('Aprovado Por', nota.utilizador_aprovador_nome or 'N/D'),
        ]
        colunas_pdf = ['Conceito', 'Valor Creditado (KZ)']
        linhas_pdf = [
            [f'CrÃ©dito referente Ã  Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor_creditado)]
        ]
        _construir_pdf_base(
            buffer, f"Nota de CrÃ©dito {nota.numero_nota}",
            "Documento de RetificaÃ§Ã£o de FaturaÃ§Ã£o", nota.estado,
            dados_kv_pdf, colunas_pdf, linhas_pdf, nota.valor_creditado
        )
        buffer.seek(0)
        anexos = [(f'NotaCredito_{nota.numero_nota}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Nota de CrÃ©dito {nota.numero_nota} â€” SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de CrÃ©dito referente Ã  factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  NÃºmero: {nota.numero_nota}
  Factura Relacionada: {nota.factura_relacionada.numero_factura}
  Valor Creditado: {fmt_kz(nota.valor_creditado)} KZ
  Motivo: {nota.motivo}
  Data: {nota.data.strftime('%d/%m/%Y')}
  Estado: {nota.estado}

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Nota de CrÃ©dito</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Nota de CrÃ©dito com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">NÃºmero:</td>
                    <td style="padding: 10px;">{nota.numero_nota}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Factura Relacionada:</td>
                    <td style="padding: 10px;">{nota.factura_relacionada.numero_factura}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Creditado:</td>
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{fmt_kz(nota.valor_creditado)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Motivo:</td>
                    <td style="padding: 10px;">{nota.motivo}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data:</td>
                    <td style="padding: 10px;">{nota.data.strftime('%d/%m/%Y')}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Nota de CrÃ©dito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
def nota_debito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} nÃ£o possui endereÃ§o de email configurado.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        dados_kv_pdf = [
            ('NIF do Cliente', nota.cliente.nif),
            ('Nome do Cliente', nota.cliente.nome),
            ('Factura Relacionada', nota.factura_relacionada.numero_factura),
            ('Motivo do DÃ©bito', nota.motivo),
            ('Data de EmissÃ£o', nota.data.strftime('%d/%m/%Y')),
            ('Criado Por', nota.utilizador_criador_nome),
        ]
        colunas_pdf = ['Conceito', 'Valor Debitado (KZ)']
        linhas_pdf = [
            [f'DÃ©bito adicional referente Ã  Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor)]
        ]
        _construir_pdf_base(
            buffer, f"Nota de DÃ©bito {nota.numero_nota}",
            "Documento de Encargo Adicional", "EMITIDA",
            dados_kv_pdf, colunas_pdf, linhas_pdf, nota.valor
        )
        buffer.seek(0)
        anexos = [(f'NotaDebito_{nota.numero_nota}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Nota de DÃ©bito {nota.numero_nota} â€” SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de DÃ©bito referente Ã  factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  NÃºmero: {nota.numero_nota}
  Factura Relacionada: {nota.factura_relacionada.numero_factura}
  Valor Debitado: {fmt_kz(nota.valor)} KZ
  Motivo: {nota.motivo}
  Data: {nota.data.strftime('%d/%m/%Y')}
  Estado: {nota.estado}

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Nota de DÃ©bito</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Nota de DÃ©bito com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">NÃºmero:</td>
                    <td style="padding: 10px;">{nota.numero_nota}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Factura Relacionada:</td>
                    <td style="padding: 10px;">{nota.factura_relacionada.numero_factura}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Debitado:</td>
                    <td style="padding: 10px; font-weight: bold; color: #dc2626;">{fmt_kz(nota.valor)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Motivo:</td>
                    <td style="padding: 10px;">{nota.motivo}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Data:</td>
                    <td style="padding: 10px;">{nota.data.strftime('%d/%m/%Y')}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Nota de DÃ©bito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:nota_debito_detalhe', pk=pk)






# ────────────────────────────────────────────────────────────────────────────────
# APIs para Auto-preenchimento de Requisição de Fundos
# ────────────────────────────────────────────────────────────────────────────────

@requer_sessao_ativa
@require_http_methods(["GET"])
def api_dados_usuario_banca(request):
    """API: Retorna dados da banca/filial do usuário logado para auto-preenchimento"""
    try:
        banca_id = request.session.get('banca_id')
        filial_id = request.session.get('colaborador_filial_id')
        
        if not banca_id:
            return JsonResponse({'success': False, 'error': 'Usuário não tem banca associada'})
        
        from rh.models import Banca, FilialBanca
        
        try:
            banca = Banca.objects.get(id=banca_id)
            banca_data = {
                'id': banca.id,
                'nome': banca.nome,
                'nif': banca.nif,
                'licenca_cdoa': banca.licenca_cdoa,
                'endereco': banca.endereco,
                'telefone': banca.telefone,
                'email': banca.email,
            }
        except Banca.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Banca não encontrada'})
        
        filial_data = None
        if filial_id:
            try:
                filial = FilialBanca.objects.get(id=filial_id, banca=banca)
                filial_data = {
                    'id': filial.id,
                    'nome': filial.nome,
                }
            except FilialBanca.DoesNotExist:
                pass
        
        return JsonResponse({
            'success': True,
            'banca': banca_data,
            'filial': filial_data
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@requer_sessao_ativa
@require_http_methods(["GET"])
def api_dados_cliente(request):
    """API: Retorna dados do cliente para auto-preenchimento"""
    try:
        cliente_id = request.GET.get('cliente_id')
        if not cliente_id:
            return JsonResponse({'success': False, 'error': 'ID do cliente é obrigatório'})
        
        # Verificar permissões
        filtro = {}
        if not _user_tem_acesso_total(request):
            usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
            if usuario_id:
                filtro['usuario_id'] = usuario_id
        
        try:
            cliente = Cliente.objects.get(id=cliente_id, **filtro)
            
            return JsonResponse({
                'success': True,
                'cliente': {
                    'id': cliente.id,
                    'nome': cliente.nome,
                    'nif': cliente.nif,
                    'email': cliente.email,
                    'telefone': cliente.telefone,
                    'localizacao': cliente.localizacao,
                }
            })
            
        except Cliente.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Cliente não encontrado'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@requer_sessao_ativa 
@require_http_methods(["GET"])
def api_processos_cliente(request):
    """API: Retorna processos aduaneiros do cliente selecionado com filtro robusto"""
    try:
        cliente_id = request.GET.get('cliente_id')
        if not cliente_id:
            return JsonResponse({'success': False, 'error': 'ID do cliente é obrigatório'})
        
        # ┌─ Validar que cliente existe e pertence ao utilizador ─────────────┐
        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except Cliente.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Cliente não encontrado'})
        
        # ┌─ Verificar permissão de acesso ao cliente ─────────────────────────┐
        if not _user_tem_acesso_total(request):
            usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
            if usuario_id and cliente.usuario_id != usuario_id:
                return JsonResponse({
                    'success': False, 
                    'error': 'Você não tem permissão para ver processos deste cliente'
                })
        
        # ┌─ Construir filtro base ───────────────────────────────────────────┐
        filtro = {
            # Filtro 1: Nome do exportador corresponde ao nome do cliente
            'exportador_nome__iexact': cliente.nome,
            # Filtro 2: Status DEVE ser 'Submetida' (apenas para criação de requisição)
            'status': 'Submetida',
        }
        
        # ┌─ Adicionar filtro por utilizador/despachante ──────────────────────┐
        if not _user_tem_acesso_total(request):
            usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
            if usuario_id:
                filtro['usuario_id'] = usuario_id
        
        # ┌─ Buscar processos com os filtros ─────────────────────────────────┐
        processos_qs = DeclaracaoUnica.objects.filter(**filtro).values(
            'id', 'numero_du', 'ref_despachante', 'exportador_nome', 
            'status', 'created_at'
        ).order_by('-created_at')[:50]  # Últimos 50 processos
        
        processos_list = list(processos_qs)
        
        return JsonResponse({
            'success': True,
            'processos': processos_list,
            'cliente_nome': cliente.nome,
            'total_encontrados': len(processos_list)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False, 
            'error': f'Erro ao carregar processos: {str(e)}'
        })


@requer_sessao_ativa
@require_http_methods(["GET"])
def api_dados_processo(request):
    """API: Retorna dados completos do processo aduaneiro com mapeamento correcto dos campos de carga"""
    try:
        processo_id = request.GET.get('processo_id')
        if not processo_id:
            return JsonResponse({'success': False, 'error': 'ID do processo é obrigatório'})
        
        filtro = {'id': processo_id}
        if not _user_tem_acesso_total(request):
            usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
            if usuario_id:
                filtro['usuario_id'] = usuario_id
        
        try:
            processo = DeclaracaoUnica.objects.get(**filtro)
            
            # Extrair dados_json
            dados_dict = {}
            if hasattr(processo, 'dados_json') and processo.dados_json:
                try:
                    import json
                    dados_dict = json.loads(processo.dados_json)
                except (json.JSONDecodeError, TypeError):
                    dados_dict = {}
            
            # Extrair adições da dados_json
            adicoes = dados_dict.get('adicoes') or []
            primeira_adicao = adicoes[0] if adicoes else {}
            
            # Helper: valor de dados_json com fallback para modelo
            def _val(json_key, model_attr=None, default=''):
                v = dados_dict.get(json_key)
                if v not in (None, '', 0):
                    return str(v).strip()
                if model_attr:
                    m = getattr(processo, model_attr, None)
                    if m not in (None, '', 0):
                        return str(m).strip()
                return default
            
            # Helper: extrair valor da primeira adição
            def _ad(val_key, default=''):
                v = primeira_adicao.get(val_key)
                if v not in (None, '', 0):
                    return str(v).strip()
                return default
            
            # Somar pesos de todas as adições
            peso_bruto_total = 0
            peso_liquido_total = 0
            for ad in adicoes:
                try:
                    peso_bruto_total += float(ad.get('peso_bruto', 0) or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    peso_liquido_total += float(ad.get('peso_liquido', 0) or 0)
                except (TypeError, ValueError):
                    pass
            # Fallback para modelo se soma for zero
            if peso_bruto_total == 0 and processo.peso_bruto:
                peso_bruto_total = float(processo.peso_bruto)
            if peso_liquido_total == 0 and processo.peso_liquido:
                peso_liquido_total = float(processo.peso_liquido)
            
            # Construir descrição concatenada de todas as adições
            descricoes = []
            for ad in adicoes:
                d = ad.get('descricao_mercadoria', '').strip()
                if d:
                    descricoes.append(d)
            descricao_final = ' | '.join(descricoes) if descricoes else ''
            if not descricao_final and processo.descricao_mercadoria:
                descricao_final = processo.descricao_mercadoria
            
            # Construir quantidade_volumes a partir da primeira adição
            qtd_volumes = ''
            nv = primeira_adicao.get('numero_volume', '').strip()
            tv = primeira_adicao.get('tipo_volume', '').strip()
            if nv or tv:
                qtd_volumes = f'{nv} {tv}'.strip()
            if not qtd_volumes:
                qtd_volumes = _val('quantidade_volumes', 'quantidade')
            
            # País de origem: da primeira adição (fallback modelo)
            pais_origem = _ad('pais_origem')
            if not pais_origem and processo.pais_origem:
                pais_origem = str(processo.pais_origem).strip()
            
            # Helper para combinar porto + país
            def _combinar_porto_pais(porto_key, pais_val):
                porto_val = _val(porto_key) or ''
                if porto_val and pais_val:
                    return f'{porto_val} / {pais_val}'
                return porto_val or pais_val or ''
            
            # ┌─ Construir resposta ─────────────────────────────────────────┐
            return JsonResponse({
                'success': True,
                'processo': {
                    'id': processo.id,
                    'numero_du': _val('numero_du', 'numero_du'),
                    'ref_despachante': _val('ref_despachante', 'ref_despachante'),
                    'regime_aduaneiro': _val('regime_aduaneiro', 'regime_aduaneiro'),
                    'exportador_nome': _val('exportador_nome', 'exportador_nome'),
                    'destinatario_nome': _val('destinatario_nome', 'destinatario_nome'),
                    'status': processo.status or 'Rascunho',
                    
                    # Dados da carga — mapeamento correcto do formulário DU
                    'numero_bl_awb': _val('numero_conhecimento'),  # DU usa "Conhecimento" não "B/L AWB"
                    'meio_transporte': _val('transporte_identidade', 'meio_transporte'),  # DU: "Identidade Meio Transporte"
                    'origem': _combinar_porto_pais('porto_embarque', pais_origem),  # DU: porto + país de origem
                    'destino': _combinar_porto_pais('porto_desembarque', dados_dict.get('pais_destino_campo53', '')),  # DU: porto + país destino automático
                    'mercadoria_descricao': descricao_final,  # Concatena descrições das adições
                    'peso_bruto_kg': str(peso_bruto_total) if peso_bruto_total > 0 else '',
                    'peso_liquido_kg': str(peso_liquido_total) if peso_liquido_total > 0 else '',
                    'cbm_metros_cubicos': _val('cbm_metros_cubicos'),  # Sem equivalente directo na DU
                    'quantidade_volumes': qtd_volumes,
                    'valor_cif': str(processo.valor_cif) if processo.valor_cif else '',
                    
                    # Dados bancários
                    'nome_banco': _val('nome_banco', 'nome_banco'),
                    'termo_pagamento': _val('termo_pagamento', 'termo_pagamento'),
                    
                    # Dados adicionais
                    'valor_fob': str(processo.valor_fob) if processo.valor_fob else '',
                    'valor_frete': str(processo.valor_frete) if processo.valor_frete else '',
                    'valor_seguro': str(processo.valor_seguro) if processo.valor_seguro else '',
                    'total_geral': str(processo.total_geral) if processo.total_geral else '',
                    
                    # Moeda e câmbio usados na DU (moeda_fob / cambio_fob)
                    'moeda_du': _val('moeda_fob'),
                    'cambio_du': _val('cambio_fob'),
                    
                    '_dados_json': dados_dict,
                }
            })
            
        except DeclaracaoUnica.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Processo não encontrado ou sem permissão de acesso'})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': f'Erro ao carregar dados: {str(e)}'})