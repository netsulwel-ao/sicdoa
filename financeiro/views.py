import json
import io
import logging
import html as _html_mod
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
from django.db import models as db_models, transaction
from django.db.models import Q, Count, Prefetch, Sum, Value
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
    Levanta ValueError se o valor não puder ser parseado.
    """
    valor_str = valor_str.strip().replace(' ', '')
    
    if not valor_str:
        raise ValueError('Valor monetário vazio')
    
    # Se tem vírgula, é formato europeu (1.234.567,89)
    if ',' in valor_str:
        valor_str = valor_str.replace('.', '').replace(',', '.')
    # Se tem ponto, precisa validar se é separador de milhar ou decimal
    elif '.' in valor_str:
        partes = valor_str.split('.')
        if len(partes) > 2:
            valor_str = valor_str.replace('.', '')
        elif len(partes) == 2 and len(partes[1]) == 3:
            valor_str = valor_str.replace('.', '')
    
    resultado = Decimal(valor_str)
    if resultado < 0:
        raise ValueError('Valor monetário negativo')
    return resultado


def _safe(text):
    """Escapa caracteres HTML/XML especiais para prevenir XSS em PDFs e emails."""
    if not text:
        return ''
    return _html_mod.escape(str(text))


def _carregar_assinatura(usuario_id):
    """Carrega a assinatura digital de um utilizador e retorna um ReportLab Image ou None."""
    if not usuario_id:
        return None
    try:
        from users.models import Usuario
        usuario = Usuario.objects.get(id=usuario_id)
        raw = getattr(usuario, 'assinatura', '') or ''
        if raw.startswith('data:image/png;base64,'):
            import base64 as _b64
            from reportlab.platypus import Image as RLImage
            from io import BytesIO
            img_data = _b64.b64decode(raw.split(',', 1)[1])
            img_buf = BytesIO(img_data)
            return RLImage(img_buf, width=3*cm, height=0.6*cm)
    except Exception:
        pass
    return None


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
    # Administradores são apenas visualizadores no módulo financeiro
    if papel == 'Administrador':
        return False
    if papel == 'Despachante Oficial':
        return True
    from users.permissoes import usuario_tem_permissao, _is_admin_ou_acesso_total
    if _is_admin_ou_acesso_total(request):
        return False
    if usuario_tem_permissao(request, 'acesso_auditoria'):
        return False
    return False


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


def safe_pdf(view_func):
    """Decorator que captura erros em PDF views e retorna 500 amigável."""
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except Exception:
            logger.exception("Erro ao gerar PDF")
            return HttpResponse(
                '<html><body><h3>Erro ao gerar PDF</h3>'
                '<p>Ocorreu um erro interno. Tente novamente ou contacte o suporte.</p>'
                '<a href="javascript:history.back()">Voltar</a></body></html>',
                status=500, content_type='text/html',
            )
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
        context['pode_escrever'] = _pode_escrever(self.request)
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
        self.object._recalcular_totais()
        self.object._gerar_assinatura_digital()
        self.object.save(update_fields=[
            'subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral',
            'assinatura_digital',
        ])
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
            
            try:
                valor = parse_valor_monetario(valor_raw)
            except ValueError:
                logger.warning("CUSTO DEBUG [CREATE]: valor inválido '%s', ignorando", valor_raw)
                continue
            
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
        qs = qs.prefetch_related(
            Prefetch('linhas', queryset=RequisicaoFundoLinha.objects.order_by('ordem'),
                     to_attr='linhas_ordenadas'),
            'facturas',
        )
        filtro = self._get_user_cliente_filter()
        if filtro:
            qs = qs.filter(**filtro)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        all_linhas = self.object.linhas_ordenadas
        context['linhas'] = all_linhas
        context['linhas_documentadas'] = [l for l in all_linhas if l.documentada]
        context['linhas_nao_documentadas'] = [l for l in all_linhas if not l.documentada]
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
        self.object.linhas.all().delete()
        self._salvar_custos(self.object)
        self.object._recalcular_totais()
        self.object._gerar_assinatura_digital()
        self.object.save(update_fields=[
            'subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral',
            'assinatura_digital',
        ])
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
            
            try:
                valor = parse_valor_monetario(valor_raw)
            except ValueError:
                logger.warning("CUSTO DEBUG [UPDATE]: valor inválido '%s', ignorando", valor_raw)
                continue
            
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


@require_POST
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
@require_POST
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


@require_POST
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

"""
View requisicao_pdf — layout reestruturado (estilo FactPlus/NETSULWEL)
usando exclusivamente os campos que já existiam na função original.

Dependência nova: qrcode
    pip install qrcode[pil]

Se preferires não gerar QR code real, substitui o bloco "QR CODE" por um
Paragraph vazio, como estava na versão anterior.
"""
import io
from datetime import datetime
from decimal import Decimal

import qrcode
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import HRFlowable

from users.models import Usuario


# ──────────────────────────────────────────────────────────────────────────
# Conversão de valores para extenso (Kwanzas)
# ──────────────────────────────────────────────────────────────────────────
_UNIDADES = ['zero', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
_DEZ_A_DEZENOVE = ['dez', 'onze', 'doze', 'treze', 'catorze', 'quinze',
                    'dezasseis', 'dezassete', 'dezoito', 'dezanove']
_DEZENAS = ['', 'dez', 'vinte', 'trinta', 'quarenta', 'cinquenta',
            'sessenta', 'setenta', 'oitenta', 'noventa']
_CENTENAS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos',
             'seiscentos', 'setecentos', 'oitocentos', 'novecentos']


def _grupo_3_digitos(n):
    """Converte um número de 0 a 999 para texto por extenso."""
    if n == 0:
        return ''
    centena = n // 100
    resto = n % 100
    partes = []
    if centena > 0:
        partes.append('cem' if n == 100 else _CENTENAS[centena])
    if resto > 0:
        if partes:
            partes.append('e')
        if resto < 10:
            partes.append(_UNIDADES[resto])
        elif resto < 20:
            partes.append(_DEZ_A_DEZENOVE[resto - 10])
        else:
            dezena, unidade = resto // 10, resto % 10
            if unidade == 0:
                partes.append(_DEZENAS[dezena])
            else:
                partes.append(f'{_DEZENAS[dezena]} e {_UNIDADES[unidade]}')
    return ' '.join(partes)


def _extenso_inteiro(n):
    if n == 0:
        return 'zero'
    escalas = [
        (1_000_000_000, 'mil milhões', 'mil milhões'),
        (1_000_000, 'milhão', 'milhões'),
        (1_000, 'mil', 'mil'),
    ]
    partes = []
    resto = n
    for valor_escala, singular, plural in escalas:
        qtd, resto = divmod(resto, valor_escala)
        if qtd > 0:
            if valor_escala == 1_000 and qtd == 1:
                partes.append('mil')
            else:
                nome = singular if qtd == 1 else plural
                partes.append(f'{_grupo_3_digitos(qtd)} {nome}')
    if resto > 0:
        partes.append(_grupo_3_digitos(resto))

    if not partes:
        return 'zero'
    if len(partes) == 1:
        return partes[0]

    ultimo_grupo = n % 1000
    usa_e = ultimo_grupo == 0 or ultimo_grupo < 100 or ultimo_grupo % 100 == 0
    if usa_e and ultimo_grupo > 0:
        return ', '.join(partes[:-1]) + ' e ' + partes[-1]
    return ', '.join(partes)


def valor_por_extenso(valor):
    """Ex.: 3499.80 -> 'Três mil e quatrocentos e noventa e nove kwanzas
    e oitenta cêntimos'"""
    valor = Decimal(valor).quantize(Decimal('0.01'))
    inteiro = int(valor)
    centavos = int((valor - inteiro) * 100)

    texto_inteiro = _extenso_inteiro(inteiro)
    moeda = 'kwanza' if inteiro == 1 else 'kwanzas'
    texto = f'{texto_inteiro} {moeda}'
    if centavos > 0:
        texto_centavos = _grupo_3_digitos(centavos)
        cent_label = 'cêntimo' if centavos == 1 else 'cêntimos'
        texto += f' e {texto_centavos} {cent_label}'
    return texto[:1].upper() + texto[1:]


# ──────────────────────────────────────────────────────────────────────────
# VIEW
# ──────────────────────────────────────────────────────────────────────────
@safe_pdf
@requer_sessao_ativa
def requisicao_pdf(request, pk):
    """Gera PDF da Requisição de Fundos com layout estilo FactPlus/NETSULWEL,
    usando os mesmos campos e dados da versão original."""

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
    COR_PRIMARIO = colors.HexColor('#0f172a')
    COR_SECUNDARIO = colors.white
    COR_CINZA = colors.HexColor('#64748b')
    COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
    COR_BORDA = colors.HexColor('#cbd5e1')
    COR_VERDE = colors.HexColor('#059669')
    COR_VERMELHO = colors.HexColor('#dc2626')
    COR_BRANCO = colors.white
    COR_HEADER = colors.white

    def st(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRIMARIO, leading=11)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    banca = requisicao.banca
    cliente = requisicao.cliente
    processo = requisicao.processo_aduaneiro

    # Despachante responsável (dono da banca)
    responsavel_nome = 'DESPACHANTE OFICIAL'
    responsavel_nif = '—'
    responsavel_cedula = '—'
    responsavel_telefone = '—'
    responsavel_email = '—'
    if banca:
        try:
            usuario_banca = Usuario.objects.get(id=banca.usuario_id)
            responsavel_nome = _safe((usuario_banca.nome or 'DESPACHANTE OFICIAL')).upper()
            responsavel_nif = _safe(usuario_banca.nif) or '—'
            responsavel_cedula = _safe(usuario_banca.cedula) or '—'
            responsavel_telefone = _safe(usuario_banca.telefone) or '—'
            responsavel_email = _safe(usuario_banca.email) or '—'
        except Exception:
            responsavel_nome = 'DESPACHANTE OFICIAL'

    agora = datetime.now()
    nif_txt = banca.nif if banca else 'N/D'
    nome_txt = _safe(banca.nome) if banca else 'Despachante Oficial'
    cdoa = _safe(banca.licenca_cdoa) if banca else '—'
    endereco = _safe(banca.endereco) if banca else '—'
    telefone = _safe(banca.telefone) if banca else '—'
    email_b = _safe(banca.email) if banca else '—'

    story = []

    # ════════════════════════════════════════════════════════════════
    # LOGO (esquerda) + QR CODE (direita)
    # ══════════════════════════════════════════════════════════════════
    logo_path = None
    if banca and hasattr(banca, 'logo') and banca.logo:
        try:
            logo_path = banca.logo.path
        except Exception:
            logo_path = None

    col_logo = Paragraph('', st('empty', fontSize=1))
    if logo_path:
        try:
            col_logo = RLImage(logo_path, width=2.4 * cm, height=1.7 * cm)
        except Exception:
            col_logo = Paragraph('', st('empty', fontSize=1))

    nr_du = processo.numero_du if processo else '—'
    merc = requisicao.mercadoria_descricao[:60] if requisicao.mercadoria_descricao else '—'

    qr_data = (
        f"=== REQUISIÇÃO DE FUNDOS ===\n"
        f"Nº: {requisicao.numero_requisicao}\n"
        f"Data: {requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else '—'}\n"
        f"Validade: {requisicao.data_validade.strftime('%d/%m/%Y') if requisicao.data_validade else '—'}\n"
        f"Estado: {requisicao.estado}\n"
        f"\n--- CLIENTE ---\n"
        f"Nome: {cliente.nome if cliente else '—'}\n"
        f"NIF: {cliente.nif if cliente else '—'}\n"
        f"Contacto: {requisicao.pessoa_contacto or '—'}\n"
        f"\n--- PROCESSO ---\n"
        f"DU: {nr_du}\n"
        f"Mercadoria: {merc}\n"
        f"Origem: {requisicao.origem or '—'}\n"
        f"Destino: {requisicao.destino or '—'}\n"
        f"Transporte: {requisicao.meio_transporte or '—'}\n"
        f"B/L/AWB: {requisicao.numero_bl_awb or '—'}\n"
        f"Valor CIF: {fmt_kz(requisicao.valor_cif or 0)} KZ\n"
        f"Peso Bruto: {requisicao.peso_bruto_kg or '—'} Kg\n"
        f"\n--- VALORES ---\n"
        f"Subtotal: {fmt_kz(requisicao.subtotal_geral or 0)} KZ\n"
        f"IVA ({requisicao.taxa_iva}%): {fmt_kz(requisicao.iva_honorarios or 0)} KZ\n"
        f"Retenção: {fmt_kz(requisicao.retencao or 0)} KZ\n"
        f"TOTAL: {fmt_kz(requisicao.total_geral or 0)} KZ\n"
        f"\n--- DESPACHANTE ---\n"
        f"Nome: {responsavel_nome}\n"
        f"NIF: {responsavel_nif}\n"
        f"Cédula: {responsavel_cedula}\n"
    )
    import qrcode as _qr
    _qr_buf = io.BytesIO()
    _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
    _qr_obj.add_data(qr_data)
    _qr_obj.make(fit=True)
    _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
    _qr_buf.seek(0)
    qr_flowable = RLImage(_qr_buf, width=1.9 * cm, height=1.9 * cm)

    top_line = Table([[col_logo, qr_flowable]], colWidths=[W - 1.9 * cm, 1.9 * cm])
    top_line.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(top_line)
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════
    # BLOCO EMPRESA (esquerda) + BLOCO CLIENTE (direita)
    # ══════════════════════════════════════════════════════════════════
    empresa_info = (
        f'<font size="9"><b>{nome_txt}</b></font><br/>'
        f'<font size="7.5" color="#334155">Residência: {endereco}</font><br/>'
        f'<font size="7.5" color="#334155">Tel: {telefone}</font><br/>'
        f'<font size="7.5" color="#334155">Email: {email_b}</font><br/>'
        f'<font size="7.5" color="#334155">NIF: {nif_txt} &nbsp;|&nbsp; Licença CDOA: {cdoa}</font>'
    )
    cli_nome = _safe(cliente.nome) if cliente else '—'
    cli_nif = _safe(cliente.nif) if cliente else '—'
    cli_end = _safe(cliente.localizacao) if cliente else '—'
    cliente_info = (
        f'<font size="7.5">Exmo.(s) Sr(s)</font><br/>'
        f'<font size="9"><b>{cli_nome}</b></font><br/>'
        f'<font size="7.5" color="#334155">{cli_end}</font><br/>'
        f'<font size="7.5" color="#334155">NIF: {cli_nif}</font>'
    )
    header_body = Table([[
        Paragraph(empresa_info, st('empresa_info', fontSize=7.5, leading=10)),
        Paragraph(cliente_info, st('cliente_info', fontSize=7.5, leading=10)),
    ]], colWidths=[W * 0.55, W * 0.45])
    header_body.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_body)
    story.append(Spacer(1, 0.35 * cm))

    # ══════════════════════════════════════════════════════════════════
    # TÍTULO DO DOCUMENTO
    # ══════════════════════════════════════════════════════════════════
    story.append(Paragraph('<font size="7.5">Original</font>', st('original', fontSize=7.5)))
    story.append(Paragraph(
        f'<font size="12"><b>Requisição de Fundos n.º {requisicao.numero_requisicao}</b></font>',
        st('titulo', fontSize=12)
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════
    # DADOS DO DOCUMENTO (linha estilo "Data do Documento | ... | V/ Ref.")
    # ══════════════════════════════════════════════════════════════════
    data_emissao = requisicao.data_emissao.strftime('%d/%m/%Y') if requisicao.data_emissao else '—'
    data_validade = requisicao.data_validade.strftime('%d/%m/%Y') if requisicao.data_validade else '—'
    moeda = requisicao.moeda_referencia or 'AOA'
    cambio = requisicao.cambio_referencia or '—'
    cli_contacto = requisicao.pessoa_contacto or '—'
    ref_processo = processo.id if processo else '—'
    nr_du = processo.numero_du if processo else '—'

    dados_doc_header = [
        Paragraph('<b>Data de Emissão</b>', st('ddh', fontSize=7.5)),
        Paragraph('<b>Data de Validade</b>', st('ddh', fontSize=7.5)),
        Paragraph('<b>Data/Hora de Emissão</b>', st('ddh', fontSize=7.5)),
        Paragraph('<b>NIF Cliente</b>', st('ddh', fontSize=7.5)),
        Paragraph('<b>V/ Ref.</b>', st('ddh', fontSize=7.5)),
    ]
    dados_doc_valores = [
        Paragraph(data_emissao, st('ddv', fontSize=7.5)),
        Paragraph(data_validade, st('ddv', fontSize=7.5)),
        Paragraph(agora.strftime('%Y-%m-%d %H:%M'), st('ddv', fontSize=7.5)),
        Paragraph(cli_nif, st('ddv', fontSize=7.5)),
        Paragraph(cli_contacto, st('ddv', fontSize=7.5)),
    ]
    t_dados_doc = Table([dados_doc_header, dados_doc_valores], colWidths=[W / 5] * 5)
    t_dados_doc.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_CINZA),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_dados_doc)
    story.append(Paragraph(
        f'<font size="7" color="#64748b">Observações: Requisição referente ao processo {ref_processo} — Nr DU {nr_du}</font>',
        st('obs', fontSize=7)
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ══════════════════════════════════════════════════════════════════
    # TABELA DE ITENS (linha a linha: Código | Descrição | Valor | Tipo | Total)
    # ══════════════════════════════════════════════════════════════════
    bl = requisicao.numero_bl_awb or '—'
    transporte = requisicao.meio_transporte or (processo.meio_transporte if processo else '—')
    origem = requisicao.origem or (
        f"{getattr(processo, 'pais_origem', '') or ''} / {getattr(processo, 'porto_embarque', '') or ''}".strip(' /') or '—'
    )
    destino = requisicao.destino or (getattr(processo, 'porto_desembarque', '') or '—')
    merc = requisicao.mercadoria_descricao or (processo.descricao_mercadoria if processo else '—')
    peso_bruto = (
        f"{requisicao.peso_bruto_kg:.2f} Kg" if requisicao.peso_bruto_kg
        else (f"{processo.peso_bruto:.2f} Kg" if processo and processo.peso_bruto else '—')
    )
    peso_liq = (
        f"{requisicao.peso_liquido_kg:.2f} Kg" if requisicao.peso_liquido_kg
        else (f"{processo.peso_liquido:.2f} Kg" if processo and processo.peso_liquido else '—')
    )
    v_cif = fmt_kz(requisicao.valor_cif) if requisicao.valor_cif else (
        fmt_kz(processo.valor_cif) if processo and processo.valor_cif else '—'
    )
    processo_total = fmt_kz(processo.total_geral) if processo and processo.total_geral else '—'

    itens_header = [
        Paragraph('<b>Código</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO)),
        Paragraph('<b>Descrição</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO)),
        Paragraph('<b>Valor</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
        Paragraph('<b>Tipo</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO)),
        Paragraph('<b>Total</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
    ]
    itens_rows = [itens_header]

    itens_rows.append([
        Paragraph('CIF', st('ic', fontSize=7)),
        Paragraph(f'Mercadoria: {merc}', st('ic', fontSize=7)),
        Paragraph(v_cif, st('ic', fontSize=7, alignment=TA_RIGHT)),
        Paragraph('Valor CIF', st('ic', fontSize=7)),
        Paragraph(v_cif, st('ic', fontSize=7, alignment=TA_RIGHT)),
    ])

    despesas_doc = requisicao.linhas.filter(documentada=True)
    total_direitos = Decimal('0')
    for idx, linha in enumerate(despesas_doc, start=1):
        if linha.valor and linha.valor > 0:
            total_direitos += linha.valor
            itens_rows.append([
                Paragraph(f'EP{idx:02d}', st('ic', fontSize=7)),
                Paragraph(linha.despesa_tipo or 'Despesa', st('ic', fontSize=7)),
                Paragraph(fmt_kz(linha.valor), st('ic', fontSize=7, alignment=TA_RIGHT, textColor=COR_PRIMARIO)),
                Paragraph('Direito (documentado)', st('ic', fontSize=7)),
                Paragraph(fmt_kz(linha.valor), st('ic', fontSize=7, alignment=TA_RIGHT)),
            ])

    despesas_nao_doc = requisicao.linhas.filter(documentada=False)
    total_despesas = Decimal('0')
    for idx, linha in enumerate(despesas_nao_doc, start=1):
        if linha.valor and linha.valor > 0:
            total_despesas += linha.valor
            itens_rows.append([
                Paragraph(f'DE{idx:02d}', st('ic', fontSize=7)),
                Paragraph(linha.despesa_tipo or 'Despesa', st('ic', fontSize=7)),
                Paragraph(fmt_kz(linha.valor), st('ic', fontSize=7, alignment=TA_RIGHT, textColor=COR_PRIMARIO)),
                Paragraph('Despesa (não documentada)', st('ic', fontSize=7)),
                Paragraph(fmt_kz(linha.valor), st('ic', fontSize=7, alignment=TA_RIGHT)),
            ])

    t_itens = Table(itens_rows, colWidths=[W * 0.10, W * 0.38, W * 0.16, W * 0.20, W * 0.16])
    t_itens.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_itens)
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════
    # IMPOSTO/IVA + REFERÊNCIA DO PROCESSO (esquerda) | SUMÁRIO (direita)
    # ══════════════════════════════════════════════════════════════════
    iva_pct = Decimal(requisicao.taxa_iva or '14') / Decimal('100')
    ret_pct = Decimal('0.065')
    sttl = requisicao.subtotal_geral or Decimal('0')
    iva_val = requisicao.iva_honorarios or Decimal('0')
    ret_val = requisicao.retencao or Decimal('0')
    total = requisicao.total_geral or Decimal('0')

    imposto_rows = [
        [Paragraph('<b>Impostos</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO)),
         Paragraph('<b>Incidência</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO)),
         Paragraph('<b>Valor</b>', st('imh', fontSize=7, textColor=COR_PRIMARIO, alignment=TA_RIGHT))],
        [Paragraph(f'IVA - {iva_pct*100:.2f}', st('imc', fontSize=7)),
         Paragraph(f'{fmt_kz(sttl)} KZ', st('imc', fontSize=7)),
         Paragraph(f'{fmt_kz(iva_val)} KZ', st('imc', fontSize=7, alignment=TA_RIGHT))],
        [Paragraph(f'Retenção - {ret_pct*100:.1f}', st('imc', fontSize=7)),
         Paragraph(f'{fmt_kz(sttl)} KZ', st('imc', fontSize=7)),
         Paragraph(f'{fmt_kz(ret_val)} KZ', st('imc', fontSize=7, alignment=TA_RIGHT))],
    ]
    t_imposto = Table(imposto_rows, colWidths=[W * 0.55 * 0.30, W * 0.55 * 0.40, W * 0.55 * 0.30])
    t_imposto.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
        ('LINEBELOW', (0, 0), (-1, 0), 1.0, COR_CINZA),
        ('LINEBELOW', (0, 1), (-1, -1), 0.3, COR_BORDA),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COR_BRANCO, COR_CINZA_CLARO]),
    ]))

    ref_texto = (
        f'<font size="7.5"><b>Referência do Processo</b></font><br/>'
        f'<font size="7" color="#334155">Nr DU: {nr_du}</font><br/>'
        f'<font size="7" color="#334155">Peso bruto/líquido: {peso_bruto} / {peso_liq}</font><br/>'
        f'<font size="7" color="#334155">Total do processo: {processo_total} KZ</font>'
    )
    bloco_esquerdo = [
        [t_imposto],
        [Spacer(1, 0.25 * cm)],
        [Paragraph(ref_texto, st('ref_proc', fontSize=7, leading=10))],
    ]
    t_bloco_esquerdo = Table(bloco_esquerdo, colWidths=[W * 0.55])
    t_bloco_esquerdo.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    valor_extenso = valor_por_extenso(total)
    sumario_rows = [
        [Paragraph('<b>Sumário</b>', st('sum_h', fontSize=8, fontName='Helvetica-Bold', textColor=COR_PRIMARIO))],
        [Spacer(1, 0.15 * cm)],
        [Paragraph(f'<font size="7">Subtotal (Direitos + Despesas): <b>{fmt_kz(sttl)} KZ</b></font>',
                   st('sum_l', fontSize=7, leading=10))],
        [Paragraph(f'<font size="7">IVA ({iva_pct*100:.0f}%): <b>{fmt_kz(iva_val)} KZ</b></font>',
                   st('sum_l', fontSize=7, leading=10))],
        [Paragraph(f'<font size="7">Retenção ({ret_pct*100:.1f}%): <b>{fmt_kz(ret_val)} KZ</b></font>',
                   st('sum_l', fontSize=7, leading=10))],
        [Spacer(1, 0.15 * cm)],
        [Paragraph(f'<font size="10" color="#0f172a"><b>Total: {fmt_kz(total)} KZ</b></font>',
                   st('sum_total', fontSize=10, leading=12))],
        [Spacer(1, 0.1 * cm)],
        [Paragraph(f'<font size="6.5" color="#64748b"><i>{valor_extenso}</i></font>',
                   st('sum_ext', fontSize=6.5, leading=8))],
    ]
    t_sumario = Table(sumario_rows, colWidths=[W * 0.35])
    t_sumario.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), COR_HEADER),
        ('TOPPADDING', (0, 0), (0, 0), 5),
        ('BOTTOMPADDING', (0, 0), (0, 0), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
    ]))
    bloco_direito = t_sumario

    t_resumo = Table([[t_bloco_esquerdo, '', '', bloco_direito]], colWidths=[W * 0.60, W * 0.02, W * 0.03, W * 0.35])
    t_resumo.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(t_resumo)
    story.append(Spacer(1, 0.2 * cm))

    # ══════════════════════════════════════════════════════════════════
    # NOTA
    # ══════════════════════════════════════════════════════════════════
    nota_box = Table([[
        Paragraph('<b>Nota</b>', st('nota_h', fontSize=7.5, textColor=COR_PRIMARIO)),
    ]], colWidths=[W])
    nota_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_SECUNDARIO),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('LEFTPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(nota_box)
    story.append(Paragraph(
        'Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
        st('nota_txt', fontSize=7, textColor=COR_SECUNDARIO)
    ))
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════
    # DESPACHANTE RESPONSÁVEL
    # ══════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.15 * cm))
    desp_box = Table([[
        Paragraph('<b>Despachante Responsável</b>', st('desp_h', fontSize=7.5, textColor=COR_PRIMARIO)),
    ]], colWidths=[W])
    desp_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('LEFTPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(desp_box)
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f'{responsavel_nome} &nbsp;|&nbsp; NIF: {responsavel_nif} &nbsp;|&nbsp; '
        f'Cédula CDOA: {responsavel_cedula}',
        st('desp_l1', fontSize=7.5, textColor=COR_PRIMARIO)
    ))
    story.append(Paragraph(
        f'Tel: {responsavel_telefone} &nbsp;|&nbsp; Email: {responsavel_email}',
        st('desp_l2', fontSize=7, textColor=COR_CINZA)
    ))
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════
    # ASSINATURA
    # ══════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.1 * cm))
    ass_data = [
        [Paragraph('<b>Recebido por:</b>', st('ass_lab', fontSize=8)),
         Paragraph('', st('ass_spc', fontSize=8))],
        [Spacer(1, 0.2 * cm), Spacer(1, 0.2 * cm)],
        [HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA),
         HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA)],
        [Paragraph('<font size="7.5"><b>Data:</b> _____/_____/______</font>', st('ass_data', fontSize=7.5)),
         Paragraph('<font size="7.5"><b>O Cliente</b></font>', st('ass_cli', fontSize=7.5, alignment=TA_CENTER))],
        [Paragraph('', st('ass_spc', fontSize=3)),
         Paragraph(f'<font size="7"><b>{cli_nome}</b></font>',
                   st('ass_nome', fontSize=7, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    assinatura = Table(ass_data, colWidths=[W / 2, W / 2])
    assinatura.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(assinatura)
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════
    # RODAPÉ: HASH + PÁGINA/DATA
    # ══════════════════════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor('#e2e2e2')))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f'<font size="6" color="#94a3b8"><b>{nome_txt} - HASH</b> &nbsp;|&nbsp; '
        f'Processado por programa válido nº35/AGT/2019<br/>'
        f'Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>',
        st('footer', fontSize=6)
    ))

    # BUILD DO PDF
    doc.build(story)

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Requisicao_{requisicao.numero_requisicao}.pdf"'
    return response

@require_POST
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
            except Exception:
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
  IVA ({requisicao.taxa_iva}% Honorários): {fmt_kz(requisicao.iva_honorarios)} KZ
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
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
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
                    <td style="padding: 10px; color: #475569;">IVA ({requisicao.taxa_iva}% Honorários):</td>
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
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

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
        
        # Retenção = 6.5% sobre Honorários do Despachante (mesmo critério do modelo RF)
        base_retencao = sum(
            (linha.valor or 0) for linha in linhas_qs
            if (linha.tipo_custo or '').strip() == 'Honorários do Despachante'
        )
        retencao = (base_retencao * Decimal('0.065')).quantize(Decimal('0.01'))
        
        subtotal = honorarios + taxas_aduaneiras + emolumentos + despesas_operacionais
        iva_pct = Decimal(requisicao.taxa_iva or '14') / Decimal('100')
        iva = (subtotal * iva_pct).quantize(Decimal('0.01'))
        valor_total = subtotal + iva - retencao
        
        return honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, retencao, valor_total
    
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
        honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, retencao, _ = _mapear_linhas(requisicao.linhas.all())
        
        factura = FacturaCliente(
            cliente=requisicao.cliente,
            processo_aduaneiro=requisicao.processo_aduaneiro,
            honorarios_despachante=honorarios,
            taxas_aduaneiras=taxas_aduaneiras,
            emolumentos=emolumentos,
            despesas_operacionais=despesas_operacionais,
            iva=iva,
            retencao=retencao,
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
    honorarios, taxas_aduaneiras, emolumentos, despesas_operacionais, iva, retencao, valor_total = _mapear_linhas(requisicao.linhas.all())
    
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


# ═══ Notas Home ═════════════════════════════════════════════════════════════

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/notas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas'
        return context


# ═══ Facturas Home ══════════════════════════════════════════════════════════

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/facturas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas'
        return context


# ═══ DU â†’ Factura Consolidation ════════════════════════════════════════════

@requer_sessao_ativa
def du_custos_json(request, pk):
    if _user_tem_acesso_total(request):
        du = get_object_or_404(DeclaracaoUnica, pk=pk, status='Aprovada')
    else:
        usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
        du = get_object_or_404(DeclaracaoUnica, pk=pk, status='Aprovada', despachante_id=usuario_id)
    taxas = Decimal(str(du.total_impostos or 0))
    emolumentos = Decimal(str(du.total_emgead or 0))
    iva_val = Decimal(str(du.iva or 0))
    base = taxas + emolumentos
    honorarios = (base * Decimal('0.05')).quantize(Decimal('0.01'))
    despesas = (base * Decimal('0.02')).quantize(Decimal('0.01'))
    total_encargos = base + honorarios + despesas + iva_val
    data = {
        'taxas_aduaneiras': float(taxas),
        'emolumentos': float(emolumentos),
        'iva': float(iva_val),
        'honorarios_despachante': float(honorarios),
        'despesas_operacionais': float(despesas),
        'outros_encargos': 0,
        'total_estimado': float(total_encargos),
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
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Sessão inválida.')
    base[scope_field] = usuario_id
    return get_object_or_404(model, **base)




# ═══ Facturas Finais ═════════════════════════════════════════════════════════

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
        base_qs = self.get_queryset()
        agg = base_qs.aggregate(
            total_valor=Sum('valor_total'),
            total_pago=Sum('valor_pago'),
            total_pendente=Sum(
                db_models.Case(
                    db_models.When(estado='Pendente', then='valor_total'),
                    default=Value(0),
                    output_field=db_models.DecimalField(),
                )
            ),
        )
        context['total_facturado'] = agg['total_valor'] or Decimal('0')
        context['total_recebido'] = agg['total_pago'] or Decimal('0')
        context['total_pendente'] = (agg['total_pendente'] or Decimal('0'))
        total_valor = context['total_facturado']
        context['percent_recebido'] = round((context['total_recebido'] / total_valor * 100), 1) if total_valor else 0
        context['total_facturas'] = base_qs.count()
        context['total_pago_count'] = base_qs.filter(estado='Paga').count()
        context['total_pendente_count'] = base_qs.filter(estado='Pendente').count()
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

        f = self.object
        context['saldo_restante'] = f.valor_total - f.valor_pago
        if f.valor_total and f.valor_total > 0:
            context['pago_percent'] = min(100, int((f.valor_pago or 0) / f.valor_total * 100))
        else:
            context['pago_percent'] = 0

        from datetime import date as _date
        hoje = _date.today()
        if f.data_vencimento:
            context['dias_restantes'] = (f.data_vencimento - hoje).days
        else:
            context['dias_restantes'] = 0

        # Taxa IVA dinâmica (da Requisição vinculada ou 14%)
        taxa_iva_pct = '14'
        if f.requisicao_fundo_id:
            try:
                _rf_iva = RequisicaoFundo.objects.filter(pk=f.requisicao_fundo_id).values_list('taxa_iva', flat=True).first()
                if _rf_iva:
                    taxa_iva_pct = _rf_iva
            except Exception:
                pass
        context['taxa_iva_pct'] = taxa_iva_pct

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


@require_POST
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


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def factura_enviar_email(request, pk):
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    cliente = factura.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:factura_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar
        from django.test import RequestFactory

        _rf = RequestFactory()
        _internal_req = _rf.get(f'/financeiro/facturas/{pk}/pdf/')
        _internal_req.session = request.session
        _internal_req.user = request.user
        _pdf_response = factura_pdf(_internal_req, pk)
        anexos = [(f'Factura_{factura.numero_factura}.pdf', _pdf_response.content, 'application/pdf')]

        assunto = f"Factura Final {factura.numero_factura} – SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Factura Final referente à prestação de serviços de despacho.

Detalhes:
  Número: {factura.numero_factura}
  Valor Total: {fmt_kz(factura.valor_total)} KZ
  Valor Pago: {fmt_kz(factura.valor_pago)} KZ
  Estado: {factura.estado}
  Data de Vencimento: {factura.data_vencimento.strftime('%d/%m/%Y')}

Agradecemos a sua preferência.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Factura Final</h2>
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
            <p>Segue em anexo a Factura Final com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
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
            <p style="margin-top: 25px;">Agradecemos a sua preferência.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Factura {factura.numero_factura} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

    return redirect('financeiro:factura_detalhe', pk=pk)


# ═══ Gestão de Recibos ═══════════════════════════════════════════════════════

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


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_recibo(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    if recibo.estado == 'Cancelado':
        messages.error(request, 'Este recibo já está cancelado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    pode_cancelar = _user_tem_acesso_total(request)
    if not pode_cancelar:
        messages.error(request, 'Não tem permissão para cancelar recibos.')
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


@requer_escrita_financeira
@requer_sessao_ativa
@require_POST
def editar_recibo(request, pk):
    from .forms import ReciboClienteUpdateForm
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    if not recibo.editavel:
        messages.error(request, 'Este recibo não pode ser editado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    pode_editar = _user_tem_acesso_total(request)
    if not pode_editar:
        messages.error(request, 'Não tem permissão para editar recibos.')
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


# ═══ Notas de Crédito ════════════════════════════════════════════════════════

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
    success_message = "Nota de Crédito emitida com sucesso!"

    def form_valid(self, form):
        usuario_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_id = usuario_id
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        form.instance.estado = 'Aprovada'
        form.instance.utilizador_aprovador_id = usuario_id
        form.instance.utilizador_aprovador_nome = usuario_data.get('nome', '')
        form.instance.data_aprovacao = timezone.now()
        response = super().form_valid(form)
        if self.object.cliente.email:
            _email_nota = {
                'nota_numero': self.object.numero_nota,
                'cliente_nome': self.object.cliente.nome,
                'valor': fmt_kz(self.object.valor_creditado),
                'motivo': self.object.motivo,
                'email': self.object.cliente.email,
            }
            import threading
            def _enviar_async():
                try:
                    from utils.email_utils import _enviar
                    _enviar(
                        f"Nota de Crédito {_email_nota['nota_numero']} emitida – SICDOA",
                        f"Prezado(a) {_email_nota['cliente_nome']},\n\n"
                        f"Foi emitida uma Nota de Crédito no valor de {_email_nota['valor']} Kz.\n"
                        f"Motivo: {_email_nota['motivo']}\n\n"
                        f"Atenciosamente,\nEquipa SICDOA",
                        '', _email_nota['email']
                    )
                except Exception:
                    logger.exception("Falha ao enviar email de Nota de Crédito %s", _email_nota['nota_numero'])
            threading.Thread(target=_enviar_async, daemon=True).start()
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Nota de Crédito"
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
    success_message = "Nota de Crédito actualizada com sucesso!"

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
        context['titulo'] = "Editar Nota de Crédito"
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


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def aprovar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_aprovar = _user_tem_acesso_total(request)
    if nota.utilizador_criador_id == usuario_id:
        pode_aprovar = False
    if not pode_aprovar:
        messages.error(request, 'Não tem permissão para aprovar esta nota de crédito.')
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
        messages.success(request, f'Nota de Crédito {nota.numero_nota} aprovada e creditada na conta corrente do cliente.')

        # Envio automático de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de Crédito {nota.numero_nota} aprovada – SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de Crédito {nota.numero_nota} foi aprovada no valor de {fmt_kz(nota.valor_creditado)} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                logger.exception("Falha ao enviar email de aprovação de Nota de Crédito %s", nota.numero_nota)
    return redirect('financeiro:nota_credito_detalhe', pk=pk)

@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def rejeitar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_rejeitar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_rejeitar:
        messages.error(request, 'Não tem permissão para rejeitar esta nota de crédito.')
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
        messages.warning(request, f'Nota de Crédito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_nota_credito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    if nota.estado not in ('Pendente', 'Aprovada'):
        messages.error(request, 'Apenas notas de crédito pendentes ou aprovadas podem ser canceladas.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_cancelar:
        messages.error(request, 'Apenas o criador ou o Administrador podem cancelar esta nota de crédito.')
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
        messages.success(request, f'Nota de Crédito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


# ═══ Notas de Débito ═════════════════════════════════════════════════════════

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
    success_message = "Nota de Débito emitida com sucesso!"

    def form_valid(self, form):
        usuario_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_id = usuario_id
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        form.instance.banca_id = self.request.session.get('banca_id') or getattr(form.instance.cliente, 'banca_id', None)
        form.instance.filial_id = self.request.session.get('colaborador_filial_id')
        form.instance.estado = 'Aprovada'
        form.instance.utilizador_aprovador_id = usuario_id
        form.instance.utilizador_aprovador_nome = usuario_data.get('nome', '')
        form.instance.data_aprovacao = timezone.now()
        response = super().form_valid(form)
        if self.object.cliente.email:
            _email_nd = {
                'nota_numero': self.object.numero_nota,
                'cliente_nome': self.object.cliente.nome,
                'valor': fmt_kz(self.object.valor),
                'motivo': self.object.motivo,
                'email': self.object.cliente.email,
            }
            import threading
            def _enviar_async():
                try:
                    from utils.email_utils import _enviar
                    _enviar(
                        f"Nota de Débito {_email_nd['nota_numero']} emitida – SICDOA",
                        f"Prezado(a) {_email_nd['cliente_nome']},\n\n"
                        f"Foi emitida uma Nota de Débito no valor de {_email_nd['valor']} Kz.\n"
                        f"Motivo: {_email_nd['motivo']}\n\n"
                        f"Atenciosamente,\nEquipa SICDOA",
                        '', _email_nd['email']
                    )
                except Exception:
                    logger.exception("Falha ao enviar email de Nota de Débito %s", _email_nd['nota_numero'])
            threading.Thread(target=_enviar_async, daemon=True).start()
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Nota de Débito"
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
    success_message = "Nota de Débito actualizada com sucesso!"

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
        context['titulo'] = "Editar Nota de Débito"
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


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def aprovar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_aprovar = _user_tem_acesso_total(request)
    if nota.utilizador_criador_id == usuario_id:
        pode_aprovar = False
    if not pode_aprovar:
        messages.error(request, 'Não tem permissão para aprovar esta nota de débito.')
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
        messages.success(request, f'Nota de Débito {nota.numero_nota} aprovada e debitada na conta corrente do cliente.')

        # Envio automático de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de Débito {nota.numero_nota} aprovada – SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de Débito {nota.numero_nota} foi aprovada no valor de {fmt_kz(nota.valor)} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                logger.exception("Falha ao enviar email de aprovação de Nota de Débito %s", nota.numero_nota)
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def rejeitar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_rejeitar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_rejeitar:
        messages.error(request, 'Não tem permissão para rejeitar esta nota de débito.')
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
        messages.warning(request, f'Nota de Débito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def cancelar_nota_debito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    if nota.estado not in ('Pendente', 'Aprovada'):
        messages.error(request, 'Apenas notas de débito pendentes ou aprovadas podem ser canceladas.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        _user_tem_acesso_total(request) or
        nota.utilizador_criador_id == usuario_id
    )
    if not pode_cancelar:
        messages.error(request, 'Apenas o criador ou o Administrador podem cancelar esta nota de débito.')
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
        messages.success(request, f'Nota de Débito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@requer_sessao_ativa
@requer_escrita_financeira
def eliminar_nota_debito(request, pk):
    if request.method != 'POST':
        return redirect('financeiro:nota_debito_lista')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    if nota.estado not in ('Pendente', 'Aprovada'):
        messages.error(request, 'Apenas notas de débito pendentes ou aprovadas podem ser eliminadas.')
        return redirect('financeiro:nota_debito_lista')
    numero = nota.numero_nota
    with transaction.atomic():
        if nota.estado == 'Aprovada' and nota.factura_relacionada_id:
            valor_nd = nota.valor or Decimal('0')
            FacturaCliente.objects.filter(pk=nota.factura_relacionada_id).update(
                ajuste_nota_debito=db_models.F('ajuste_nota_debito') - valor_nd,
                valor_total=db_models.F('valor_total') - valor_nd,
            )
            cliente = Cliente.objects.select_for_update().get(pk=nota.cliente.pk)
            cliente.saldo_conta_corrente += valor_nd
            cliente.save(update_fields=['saldo_conta_corrente'])
    nota.delete()
    messages.success(request, f'Nota de Débito {numero} eliminada com sucesso.')
    return redirect('financeiro:nota_debito_lista')


@requer_sessao_ativa
@requer_escrita_financeira
def eliminar_nota_credito(request, pk):
    if request.method != 'POST':
        return redirect('financeiro:nota_credito_lista')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    if nota.estado not in ('Pendente', 'Aprovada'):
        messages.error(request, 'Apenas notas de crédito pendentes ou aprovadas podem ser eliminadas.')
        return redirect('financeiro:nota_credito_lista')
    numero = nota.numero_nota
    with transaction.atomic():
        if nota.estado == 'Aprovada' and nota.factura_relacionada_id:
            valor_nc = nota.valor_creditado or Decimal('0')
            FacturaCliente.objects.filter(pk=nota.factura_relacionada_id).update(
                ajuste_nota_credito=db_models.F('ajuste_nota_credito') - valor_nc,
                valor_total=db_models.F('valor_total') + valor_nc,
            )
            cliente = Cliente.objects.select_for_update().get(pk=nota.cliente.pk)
            cliente.saldo_conta_corrente -= valor_nc
            cliente.save(update_fields=['saldo_conta_corrente'])
    nota.delete()
    messages.success(request, f'Nota de Crédito {numero} eliminada com sucesso.')
    return redirect('financeiro:nota_credito_lista')


# ═══ Facturas-Recibo ═════════════════════════════════════════════════════════

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

@require_POST
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


# ═══ Geração de PDFs ═════════════════════════════════════════════════════════

def _gerar_qr_code_flowable(dados_texto, size=1.8*cm):
    import qrcode as _qr
    from reportlab.platypus import Image as RLImage
    _qr_buf = io.BytesIO()
    _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
    _qr_obj.add_data(dados_texto)
    _qr_obj.make(fit=True)
    _qr_obj.make_image(fill_color='black', back_color='white').save(_qr_buf, format='PNG')
    _qr_buf.seek(0)
    return RLImage(_qr_buf, width=size, height=size)

def _construir_pdf_base(buffer, titulo, subtitulo, info_geral, dados_kv, tabela_colunas, tabela_linhas, total_geral, qr_flowable=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=0.8*cm, bottomMargin=1.0*cm,
        title=titulo,
    )
    W = A4[0] - 2.4*cm

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

    # Cabeçalho CDOA + QR Code
    if qr_flowable:
        cdoa_header = Table([
            [
                Paragraph('<font color="white"><b>REPÚBLICA DE ANGOLA</b><br/><font size="8">CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)</font></font>',
                           ParagraphStyle('cdoa_top', fontSize=11, fontName='Helvetica-Bold', alignment=0, leading=14)),
                qr_flowable
            ]
        ], colWidths=[W - 2.0*cm, 2.0*cm])
    else:
        cdoa_header = Table([
            [
                Paragraph('<font color="white"><b>REPÚBLICA DE ANGOLA</b><br/><font size="8">CÂMARA DOS DESPACHANTES OFICIAIS ADUANEIROS (CDOA)</font></font>',
                           ParagraphStyle('cdoa_top', fontSize=11, fontName='Helvetica-Bold', alignment=0, leading=14)),
                Paragraph(f'<font color="{cor_cdoa_gold}"><b>{info_geral}</b></font>',
                           ParagraphStyle('cdoa_right', fontSize=10, fontName='Helvetica-Bold', alignment=2))
            ]
        ], colWidths=[W - 5.5*cm, 5.5*cm])
    cdoa_header.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_cdoa),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(cdoa_header)
    story.append(Spacer(1, 0.3*cm))

    # Título do documento
    story.append(Paragraph(titulo.upper(), ParagraphStyle('doc_titulo', fontSize=16, fontName='Helvetica-Bold', textColor=cor_cdoa, spaceAfter=2)))
    story.append(Paragraph(subtitulo, s_subtitulo))
    story.append(HRFlowable(width=W, thickness=1.5, color=cor_cdoa_gold, spaceAfter=6))

    # Tabela KV
    rows = []
    for k, v in dados_kv:
        rows.append([Paragraph(str(k), s_small), Paragraph(str(v) if v else 'N/D', s_normal)])
    t_kv = Table(rows, colWidths=[5.0*cm, W - 5.0*cm])
    t_kv.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), cor_label_bg),
        ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (1, 0), (1, -1), [colors.white, cor_linha_par]),
    ]))
    story.append(t_kv)
    story.append(Spacer(1, 0.3*cm))

    # Tabela de Detalhes
    if tabela_colunas and tabela_linhas:
        story.append(Paragraph("<b>DETALHE DOS CUSTOS / VALORES</b>", ParagraphStyle('det', fontSize=9, fontName='Helvetica-Bold', textColor=cor_cabecalho, spaceAfter=4)))
        t_data = [tabela_colunas]
        for row in tabela_linhas:
            t_data.append([Paragraph(str(cell), s_normal) for cell in row])
        
        t_det = Table(t_data, colWidths=[W - 3.5*cm, 3.5*cm])
        t_det.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), cor_cabecalho),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, cor_borda),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, cor_linha_par]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        story.append(t_det)
        story.append(Spacer(1, 0.25*cm))

    # Total Geral
    t_tot = Table([[
        Paragraph('<b>TOTAL</b>', ParagraphStyle('tp', fontSize=10, fontName='Helvetica-Bold', textColor=cor_cabecalho)),
        Paragraph(f'<b>{fmt_kz(total_geral)} KZ</b>', ParagraphStyle('tv', fontSize=10, fontName='Helvetica-Bold', textColor=cor_cabecalho, alignment=2)),
    ]], colWidths=[W - 3.5*cm, 3.5*cm])
    t_tot.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), cor_label_bg),
        ('LINEABOVE', (0, 0), (-1, 0), 1.5, cor_cabecalho),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_tot)

    # Assinatura
    story.append(Spacer(1, 0.8*cm))
    _ass_img = _carregar_assinatura(banca.usuario_id if banca else None)
    if _ass_img:
        story.append(_ass_img)
        story.append(Spacer(1, 0.1*cm))
        story.append(Paragraph('Assinatura do Despachante', ParagraphStyle('ass', fontSize=8, fontName='Helvetica', alignment=1)))
    else:
        story.append(HRFlowable(width=6*cm, thickness=0.5, color=colors.HexColor('#94a3b8'), hAlign='CENTER'))
        story.append(Paragraph('Assinatura do Despachante', ParagraphStyle('ass', fontSize=8, fontName='Helvetica', alignment=1)))

    doc.build(story)


def _construir_pdf_documento(
    buffer, titulo, subtitulo, banca, cliente,
    numero_doc, data_emissao, data_validade=None,
    dados_doc_header=None, dados_doc_valores=None,
    tabela_colunas=None, tabela_linhas=None,
    sumario_linhas=None, total_geral=0,
    nota_texto=None, qr_flowable=None,
):
    """Constrói PDF no mesmo padrão visual da Requisição de Fundos:
    Logo+QR, Empresa/Cliente lado a lado, título, dados do documento,
    tabela de itens, sumário, assinatura e rodapé."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.flowables import HRFlowable
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from datetime import datetime
    from users.models import Usuario

    PAGE_W, PAGE_H = A4
    MARGIN = 0.7 * cm
    W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.5 * cm, bottomMargin=1.0 * cm,
        title=titulo,
    )

    COR_PRIMARIO = colors.HexColor('#0f172a')
    COR_SECUNDARIO = colors.white
    COR_CINZA = colors.HexColor('#64748b')
    COR_CINZA_CLARO = colors.HexColor('#f1f5f9')
    COR_BORDA = colors.HexColor('#cbd5e1')
    COR_BRANCO = colors.white
    COR_HEADER = colors.white

    def st(name, **kw):
        defaults = dict(fontName='Helvetica', fontSize=9, textColor=COR_PRIMARIO, leading=11)
        defaults.update(kw)
        return ParagraphStyle(name, **defaults)

    agora = datetime.now()

    nif_txt = banca.nif if banca else 'N/D'
    nome_txt = _safe(banca.nome) if banca else 'Despachante Oficial'
    cdoa = _safe(banca.licenca_cdoa) if banca else '—'
    endereco = _safe(banca.endereco) if banca else '—'
    telefone = _safe(banca.telefone) if banca else '—'
    email_b = _safe(banca.email) if banca else '—'

    # Despachante responsável
    responsavel_nome = 'DESPACHANTE OFICIAL'
    responsavel_nif = '—'
    responsavel_cedula = '—'
    responsavel_telefone = '—'
    responsavel_email = '—'
    if banca:
        try:
            usuario_banca = Usuario.objects.get(id=banca.usuario_id)
            responsavel_nome = _safe((usuario_banca.nome or 'DESPACHANTE OFICIAL')).upper()
            responsavel_nif = _safe(usuario_banca.nif) or '—'
            responsavel_cedula = _safe(usuario_banca.cedula) or '—'
            responsavel_telefone = _safe(usuario_banca.telefone) or '—'
            responsavel_email = _safe(usuario_banca.email) or '—'
        except Exception:
            pass

    story = []

    # LOGO + QR CODE
    logo_path = None
    if banca and hasattr(banca, 'logo') and banca.logo:
        try:
            logo_path = banca.logo.path
        except Exception:
            pass

    col_logo = Paragraph('', st('empty', fontSize=1))
    if logo_path:
        try:
            col_logo = RLImage(logo_path, width=2.4 * cm, height=1.7 * cm)
        except Exception:
            pass

    qr_cell = qr_flowable if qr_flowable else Paragraph('', st('empty', fontSize=1))
    top_line = Table([[col_logo, qr_cell]], colWidths=[W - 1.9 * cm, 1.9 * cm])
    top_line.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(top_line)
    story.append(Spacer(1, 0.15 * cm))

    # EMPRESA (esq) + CLIENTE (dir)
    cli_nome = _safe(cliente.nome) if cliente else '—'
    cli_nif = _safe(cliente.nif) if cliente else '—'
    cli_end = _safe(getattr(cliente, 'localizacao', '')) or '—'
    empresa_info = (
        f'<font size="9"><b>{nome_txt}</b></font><br/>'
        f'<font size="7.5" color="#334155">Residência: {endereco}</font><br/>'
        f'<font size="7.5" color="#334155">Tel: {telefone}</font><br/>'
        f'<font size="7.5" color="#334155">Email: {email_b}</font><br/>'
        f'<font size="7.5" color="#334155">NIF: {nif_txt} &nbsp;|&nbsp; Licença CDOA: {cdoa}</font>'
    )
    cliente_info = (
        f'<font size="7.5">Exmo.(s) Sr(s)</font><br/>'
        f'<font size="9"><b>{cli_nome}</b></font><br/>'
        f'<font size="7.5" color="#334155">{cli_end}</font><br/>'
        f'<font size="7.5" color="#334155">NIF: {cli_nif}</font>'
    )
    header_body = Table([[
        Paragraph(empresa_info, st('empresa_info', fontSize=7.5, leading=10)),
        Paragraph(cliente_info, st('cliente_info', fontSize=7.5, leading=10)),
    ]], colWidths=[W * 0.55, W * 0.45])
    header_body.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_body)
    story.append(Spacer(1, 0.35 * cm))

    # TÍTULO
    story.append(Paragraph('<font size="7.5">Original</font>', st('original', fontSize=7.5)))
    story.append(Paragraph(
        f'<font size="12"><b>{titulo}</b></font>',
        st('titulo', fontSize=12)
    ))
    if subtitulo:
        story.append(Paragraph(f'<font size="8" color="#64748b">{subtitulo}</font>', st('subtitulo', fontSize=8)))
    story.append(Spacer(1, 0.2 * cm))

    # DADOS DO DOCUMENTO (linha)
    if dados_doc_header and dados_doc_valores:
        ncols = len(dados_doc_header)
        t_dados = Table([dados_doc_header, dados_doc_valores], colWidths=[W / ncols] * ncols)
        t_dados.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_CINZA),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_dados)
        story.append(Spacer(1, 0.3 * cm))

    # TABELA DE ITENS
    if tabela_colunas and tabela_linhas:
        itens_header = [
            Paragraph(f'<b>{c}</b>', st('ih', fontSize=7.5, textColor=COR_PRIMARIO))
            for c in tabela_colunas
        ]
        itens_rows = [itens_header]
        for row in tabela_linhas:
            itens_rows.append([Paragraph(str(cell), st('ic', fontSize=7)) for cell in row])

        ncols = len(tabela_colunas)
        col_w = W / ncols
        t_itens = Table(itens_rows, colWidths=[col_w] * ncols)
        t_itens.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, COR_BORDA),
            ('LINEBELOW', (0, 1), (-1, -1), 0.3, colors.HexColor('#e2e2e2')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_itens)
        story.append(Spacer(1, 0.2 * cm))

    # SUMÁRIO (direita)
    if sumario_linhas is not None:
        sumario_rows = [
            [Paragraph('<b>Sumário</b>', st('sum_h', fontSize=8, fontName='Helvetica-Bold', textColor=COR_PRIMARIO))],
            [Spacer(1, 0.15 * cm)],
        ]
        for label, val in sumario_linhas:
            sumario_rows.append([
                Paragraph(f'<font size="7">{label}: <b>{val}</b></font>',
                          st('sum_l', fontSize=7, leading=10))
            ])
        sumario_rows.append([Spacer(1, 0.15 * cm)])
        sumario_rows.append([
            Paragraph(f'<font size="10" color="#0f172a"><b>Total: {fmt_kz(total_geral)} KZ</b></font>',
                      st('sum_total', fontSize=10, leading=12))
        ])
        valor_ext = valor_por_extenso(total_geral)
        sumario_rows.append([Spacer(1, 0.1 * cm)])
        sumario_rows.append([
            Paragraph(f'<font size="6.5" color="#64748b"><i>{valor_ext}</i></font>',
                      st('sum_ext', fontSize=6.5, leading=8))
        ])
        t_sumario = Table(sumario_rows, colWidths=[W * 0.35])
        t_sumario.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), COR_HEADER),
            ('TOPPADDING', (0, 0), (0, 0), 5),
            ('BOTTOMPADDING', (0, 0), (0, 0), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
        ]))
        story.append(t_sumario)
        story.append(Spacer(1, 0.2 * cm))

    # NOTA
    if nota_texto:
        nota_box = Table([[
            Paragraph('<b>Nota</b>', st('nota_h', fontSize=7.5, textColor=COR_PRIMARIO)),
        ]], colWidths=[W])
        nota_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), COR_SECUNDARIO),
            ('TOPPADDING', (0, 0), (-1, 0), 4),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
            ('LEFTPADDING', (0, 0), (-1, 0), 6),
        ]))
        story.append(nota_box)
        story.append(Paragraph(nota_texto, st('nota_txt', fontSize=7, textColor=COR_SECUNDARIO)))
        story.append(Spacer(1, 0.15 * cm))

    # DESPACHANTE RESPONSÁVEL
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.15 * cm))
    desp_box = Table([[
        Paragraph('<b>Despachante Responsável</b>', st('desp_h', fontSize=7.5, textColor=COR_PRIMARIO)),
    ]], colWidths=[W])
    desp_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('TOPPADDING', (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('LEFTPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(desp_box)
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f'{responsavel_nome} &nbsp;|&nbsp; NIF: {responsavel_nif} &nbsp;|&nbsp; '
        f'Cédula CDOA: {responsavel_cedula}',
        st('desp_l1', fontSize=7.5, textColor=COR_PRIMARIO)
    ))
    story.append(Paragraph(
        f'Tel: {responsavel_telefone} &nbsp;|&nbsp; Email: {responsavel_email}',
        st('desp_l2', fontSize=7, textColor=COR_CINZA)
    ))
    story.append(Spacer(1, 0.15 * cm))

    # ASSINATURA DO DESPACHANTE
    _ass_img_construir = _carregar_assinatura(banca.usuario_id if banca else None)
    if _ass_img_construir:
        story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
        story.append(Spacer(1, 0.1 * cm))
        _ass_tbl = Table([[_ass_img_construir, ''],
                          [Paragraph('<font size="7"><b>Assinatura do Despachante</b></font>',
                                     st('ass_desp_label', fontSize=7, alignment=TA_CENTER)),
                           Paragraph(f'<font size="7"><b>{responsavel_nome}</b></font>',
                                     st('ass_desp_nome', fontSize=7, alignment=TA_CENTER))]],
                         colWidths=[W/2, W/2])
        _ass_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(_ass_tbl)
        story.append(Spacer(1, 0.15 * cm))

    # ASSINATURA DO CLIENTE
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.1 * cm))
    ass_data = [
        [Paragraph('<b>Recebido por:</b>', st('ass_lab', fontSize=8)),
         Paragraph('', st('ass_spc', fontSize=8))],
        [Spacer(1, 0.2 * cm), Spacer(1, 0.2 * cm)],
        [HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA),
         HRFlowable(width=5.5 * cm, thickness=0.8, color=COR_CINZA)],
        [Paragraph('<font size="7.5"><b>Data:</b> _____/_____/______</font>', st('ass_data', fontSize=7.5)),
         Paragraph('<font size="7.5"><b>O Cliente</b></font>', st('ass_cli', fontSize=7.5, alignment=TA_CENTER))],
        [Paragraph('', st('ass_spc', fontSize=3)),
         Paragraph(f'<font size="7"><b>{cli_nome}</b></font>',
                   st('ass_nome', fontSize=7, fontName='Helvetica-Bold', alignment=TA_CENTER))],
    ]
    assinatura = Table(ass_data, colWidths=[W / 2, W / 2])
    assinatura.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(assinatura)
    story.append(Spacer(1, 0.15 * cm))

    # RODAPÉ
    story.append(HRFlowable(width=W, thickness=0.5, color=colors.HexColor('#e2e2e2')))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f'<font size="6" color="#94a3b8"><b>{nome_txt} - HASH</b> &nbsp;|&nbsp; '
        f'Processado por programa válido nº35/AGT/2019<br/>'
        f'Pág. 1 / 1 &nbsp;&nbsp; {agora.strftime("%H:%M:%S")} &nbsp;&nbsp; {agora.strftime("%d/%m/%Y")}</font>',
        st('footer', fontSize=6)
    ))

    doc.build(story)


@safe_pdf
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
    from users.models import Usuario

    PAGE_W, PAGE_H = A4
    MARGIN = 0.8 * cm
    W = PAGE_W - 2 * MARGIN

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=0.4 * cm, bottomMargin=1.0 * cm,
        title=f"Factura {factura.numero_factura}",
    )

    # ── Cores ─────────────────────────────────────────────────────────────────
    COR_PRETO    = colors.HexColor('#0f172a')
    COR_CINZA    = colors.HexColor('#64748b')
    COR_CLARO    = colors.HexColor('#f1f5f9')
    COR_BORDA    = colors.HexColor('#cbd5e1')
    COR_HEADER   = colors.white
    COR_PRIMARIO = colors.HexColor('#0f172a')
    COR_VERMELHO = colors.white
    COR_BRANCO   = colors.white
    COR_VERDE    = colors.HexColor('#059669')
    COR_CINZA_CLARO = colors.HexColor('#f1f5f9')

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
    s_th       = st('th', fontName='Helvetica-Bold', fontSize=7, textColor=COR_PRIMARIO, alignment=TA_CENTER, leading=9)
    s_td       = st('td', fontSize=8, leading=10)
    s_td_right = st('td_r', fontSize=8, leading=10, alignment=TA_RIGHT)
    s_td_cent  = st('td_c', fontSize=8, leading=10, alignment=TA_CENTER)

    banca   = factura.banca
    cliente = factura.cliente
    processo = factura.processo_aduaneiro

    # Buscar dados do despachante responsável (dono da banca)
    responsavel_nome = 'DESPACHANTE OFICIAL'
    responsavel_nif = '—'
    responsavel_cedula = '—'
    responsavel_telefone = '—'
    responsavel_email = '—'
    if banca:
        try:
            usuario_banca = Usuario.objects.get(id=banca.usuario_id)
            responsavel_nome = _safe((usuario_banca.nome or 'DESPACHANTE OFICIAL')).upper()
            responsavel_nif = _safe(usuario_banca.nif) or '—'
            responsavel_cedula = _safe(usuario_banca.cedula) or '—'
            responsavel_telefone = _safe(usuario_banca.telefone) or '—'
            responsavel_email = _safe(usuario_banca.email) or '—'
        except Exception:
            responsavel_nome = 'DESPACHANTE OFICIAL'

    story = []

    # ──────────────────────────────────────────────────────────────────────────
    # HEADER: Logo + Pág (linha 1) | Despachante + Dados Documento (linha 2)
    # ──────────────────────────────────────────────────────────────────────────
    agora = datetime.now()
    nif_txt = banca.nif if banca else 'N/D'
    nome_txt = _safe(banca.nome) if banca else 'Despachante Oficial'
    cdoa = _safe(banca.licenca_cdoa) if banca else '—'
    endereco = _safe(banca.endereco) if banca else '—'
    telefone = _safe(banca.telefone) if banca else '—'
    email_b = _safe(banca.email) if banca else '—'

    logo_path = None
    if banca and hasattr(banca, 'logo') and banca.logo:
        try:
            logo_path = banca.logo.path
        except Exception:
            logo_path = None

    col_logo = Paragraph('', s_small)
    if logo_path:
        try:
            col_logo = RLImage(logo_path, width=2.2 * cm, height=1.6 * cm)
        except Exception:
            col_logo = Paragraph('', s_small)

    # Linha 1: Logo (esquerda) — QR Code será adicionado depois
    top_line = Table([[
        col_logo, ''
    ]], colWidths=[W - 1.9 * cm, 1.9 * cm])
    top_line.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    # Linha 2: Identificação do Despachante (esquerda) + Dados do Documento (direita)
    despachante_info = (
        f'<font size="7" color="{COR_VERDE.hexval()}"><b>DESPACHANTE: {responsavel_nome}</b></font><br/>'
        f'<font size="6.5" color="#64748b">NIF: {responsavel_nif}</font><br/>'
        f'<font size="6.5" color="#64748b">Cédula CDOA: {responsavel_cedula}</font><br/>'
        f'<font size="6.5" color="#64748b">Tel: {responsavel_telefone} &nbsp;|&nbsp; Email: {responsavel_email}</font>'
    )

    data_emissao_f = factura.data_emissao.strftime('%d/%m/%Y') if factura.data_emissao else '—'
    data_venc = factura.data_vencimento.strftime('%d/%m/%Y') if factura.data_vencimento else '—'
    moeda_fact = getattr(getattr(factura, 'requisicao_fundo', None), 'moeda_referencia', '') or 'AOA'

    doc_info = (
        f'<font size="7" color="#475569"><b>Dados do Documento</b></font><br/>'
        f'<font size="6.5" color="#64748b"><b>Tipo:</b> Factura Final</font><br/>'
        f'<font size="6.5" color="#64748b"><b>Nº:</b> {factura.numero_factura}</font><br/>'
        f'<font size="6.5" color="#64748b"><b>Emissão:</b> {data_emissao_f}</font><br/>'
        f'<font size="6.5" color="#64748b"><b>Vencimento:</b> {data_venc}</font><br/>'
        f'<font size="6.5" color="#64748b"><b>Moeda:</b> {moeda_fact}</font>'
    )

    header_body = Table([[
        Paragraph(despachante_info, st('desp_info', fontSize=6.5, leading=9)),
        Paragraph(doc_info, st('doc_info', fontSize=6.5, leading=9, alignment=TA_RIGHT)),
    ]], colWidths=[W * 0.55, W * 0.45])
    header_body.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_body)
    story.append(Spacer(1, 0.06 * cm))

    # HASH e versão do sistema
    story.append(Paragraph(
        f'<font size="6" color="#94a3b8"><b>{nome_txt} - HASH</b> &nbsp;|&nbsp; Processado por programa válido nº35/AGT/2019</font>',
        st('hash_line', fontSize=6)
    ))
    story.append(Spacer(1, 0.06 * cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=COR_BORDA))
    story.append(Spacer(1, 0.06 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 3 — Barra do número da fatura
    # ══════════════════════════════════════════════════════════════════════════
    t_num = Table([[
        Paragraph(f'<b>FACTURA FT {factura.numero_factura}</b>',
                  st('num_ft', fontSize=10, fontName='Helvetica-Bold', textColor=COR_PRIMARIO)),
        Paragraph(f'<font size="9" color="#0f172a">Fatura Nº: {factura.numero_factura}</font>',
                  st('num_ft2', fontSize=9, textColor=COR_PRIMARIO, alignment=TA_RIGHT)),
    ]], colWidths=[W * 0.6, W * 0.4])
    t_num.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_HEADER),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_num)
    story.append(Spacer(1, 0.06 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 4 — Dados do Cliente + Referências do Processo Aduaneiro
    # ══════════════════════════════════════════════════════════════════════════
    # ── Dados do Cliente ────────────────────────────────────────────────────
    cli_nome  = _safe(cliente.nome) if cliente else '—'
    cli_nif   = _safe(cliente.nif) if cliente else '—'
    cli_end   = _safe(cliente.localizacao) if cliente else '—'
    cli_tel   = _safe(cliente.telefone) if cliente else '—'
    cli_email = _safe(cliente.email) if cliente else '—'
    cli_contacto = getattr(factura.requisicao_fundo, 'pessoa_contacto', '—') if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo else '—'

    cliente_rows = [
        [Paragraph('<b>Dados do Cliente (Importador/Exportador)</b>',
                   st('sec_h', fontName='Helvetica-Bold', fontSize=7.5, textColor=COR_PRIMARIO)), '', ''],
        [Paragraph('<font size="7"><b>Nome/Firma:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_nome}</font>', st('cl')),
         Paragraph('<font size="7"><b>NIF:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_nif}</font>', st('cl'))],
        [Paragraph('<font size="7"><b>Endereço:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_end}</font>', st('cl')),
         Paragraph('<font size="7"><b>Contacto:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_contacto}</font>', st('cl'))],
        [Paragraph('<font size="7"><b>Tel:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_tel}</font>', st('cl')),
         Paragraph('<font size="7"><b>Email:</b></font>', st('cl')),
         Paragraph(f'<font size="7">{cli_email}</font>', st('cl'))],
    ]
    t_cliente = Table(cliente_rows, colWidths=[W * 0.12, W * 0.38, W * 0.10, W * 0.40])
    t_cliente.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR_PRIMARIO),
        ('SPAN', (0, 0), (-1, 0)),
        ('GRID', (0, 0), (-1, -1), 0.4, COR_BORDA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, COR_CINZA_CLARO]),
    ]))
    story.append(t_cliente)
    story.append(Spacer(1, 0.1 * cm))

    # ── Referências do Processo Aduaneiro (Carga) ──────────────────────────
    ref_processo = processo.id if processo else '—'
    nr_du = processo.numero_du if processo else '—'
    bl_awb = getattr(factura.requisicao_fundo, 'numero_bl_awb', '') if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo else ''
    transporte = getattr(factura.requisicao_fundo, 'meio_transporte', '') if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo else (processo.meio_transporte if processo else '—')
    transporte = transporte or '—'
    origem = getattr(getattr(factura, 'requisicao_fundo', None), 'origem', '') or (getattr(processo, 'pais_origem', '') or '') + ' / ' + (getattr(processo, 'porto_embarque', '') or '')
    origem = origem.strip(' /') or '—'
    destino = getattr(getattr(factura, 'requisicao_fundo', None), 'destino', '') or (getattr(processo, 'porto_desembarque', '') or '—')
    merc = getattr(getattr(factura, 'requisicao_fundo', None), 'mercadoria_descricao', '') or (processo.descricao_mercadoria if processo else '—')
    peso_bruto = ''
    peso_liq = ''
    cbm = ''
    volumes = ''
    v_cif_proc = ''
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        rf = factura.requisicao_fundo
        peso_bruto = f"{rf.peso_bruto_kg:.2f} Kg" if rf.peso_bruto_kg else ''
        peso_liq = f"{rf.peso_liquido_kg:.2f} Kg" if rf.peso_liquido_kg else ''
        cbm = f"{rf.cbm_metros_cubicos:.3f}" if rf.cbm_metros_cubicos else ''
        volumes = rf.quantidade_volumes or ''
        v_cif_proc = fmt_kz(rf.valor_cif) if rf.valor_cif else ''
    if not peso_bruto and processo and hasattr(processo, 'peso_bruto') and processo.peso_bruto:
        peso_bruto = f"{processo.peso_bruto:.2f} Kg"
    if not peso_liq and processo and hasattr(processo, 'peso_liquido') and processo.peso_liquido:
        peso_liq = f"{processo.peso_liquido:.2f} Kg"
    if not v_cif_proc and processo and processo.valor_cif:
        v_cif_proc = fmt_kz(processo.valor_cif)

    # Valor Aduaneiro = total geral do processo aduaneiro
    valor_aduaneiro = ''
    if processo and processo.total_geral:
        valor_aduaneiro = fmt_kz(processo.total_geral)

    processo_rows = [
        [Paragraph('<b>Referências do Processo Aduaneiro (Carga)</b>',
                   st('sec_h', fontName='Helvetica-Bold', fontSize=7.5, textColor=COR_PRIMARIO)), '', ''],
        [Paragraph('<font size="7"><b>Ref. Interna:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{ref_processo}</font>', st('pr')),
         Paragraph('<font size="7"><b>Nr DU:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{nr_du}</font>', st('pr'))],
        [Paragraph('<font size="7"><b>Documento Transporte:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{bl_awb or "—"}</font>', st('pr')),
         Paragraph('<font size="7"><b>Navio/Voo:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{transporte}</font>', st('pr'))],
        [Paragraph('<font size="7"><b>Origem:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{origem}</font>', st('pr')),
         Paragraph('<font size="7"><b>Destino:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{destino}</font>', st('pr'))],
        [Paragraph('<font size="7"><b>Mercadoria:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{merc}</font>', st('pr')),
         Paragraph('<font size="7"><b>Valor CIF:</b></font>', st('pr')),
         Paragraph(f'<font size="7">{v_cif_proc or "—"}</font>', st('pr'))],
        [Paragraph('<font size="7"><b>Valor Aduaneiro:</b></font>', st('pr', fontName='Helvetica-Bold')),
         Paragraph(f'<font size="7">{valor_aduaneiro or "—"} KZ</font>', st('pr')),
         Paragraph('', st('pr')), Paragraph('', st('pr'))],
    ]
    t_processo = Table(processo_rows, colWidths=[W * 0.16, W * 0.34, W * 0.13, W * 0.37])
    t_processo.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COR_HEADER),
        ('TEXTCOLOR', (0, 0), (-1, 0), COR_PRIMARIO),
        ('SPAN', (0, 0), (-1, 0)),
        ('GRID', (0, 0), (-1, -1), 0.4, COR_BORDA),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, COR_CINZA_CLARO]),
    ]))
    story.append(t_processo)
    story.append(Spacer(1, 0.1 * cm))

    # QR Code da Factura (após todas as variáveis estarem definidas)
    nr_du_qr = processo.numero_du if processo else '—'
    merc_qr = (getattr(getattr(factura, 'requisicao_fundo', None), 'mercadoria_descricao', '') or '')[:60] or '—'

    # Taxa IVA para QR code e resumo
    factura_iva_pct = Decimal('14')
    if factura.requisicao_fundo_id:
        try:
            _rf_iva = RequisicaoFundo.objects.filter(pk=factura.requisicao_fundo_id).values_list('taxa_iva', flat=True).first()
            if _rf_iva:
                factura_iva_pct = Decimal(_rf_iva)
        except Exception:
            pass

    qr_data = (
        f"=== FACTURA FINAL ===\n"
        f"Nº: {factura.numero_factura}\n"
        f"Data: {data_emissao_f}\n"
        f"Vencimento: {data_venc}\n"
        f"Estado: {factura.estado}\n"
        f"\n--- CLIENTE ---\n"
        f"Nome: {cli_nome}\n"
        f"NIF: {cli_nif}\n"
        f"\n--- PROCESSO ---\n"
        f"DU: {nr_du_qr}\n"
        f"Mercadoria: {merc_qr}\n"
        f"Origem: {origem}\n"
        f"Destino: {destino}\n"
        f"Transporte: {transporte}\n"
        f"Valor CIF: {v_cif_proc or '—'} KZ\n"
        f"\n--- VALORES ---\n"
        f"Honorários: {fmt_kz(factura.honorarios_despachante)} KZ\n"
        f"Taxas Aduaneiras: {fmt_kz(factura.taxas_aduaneiras)} KZ\n"
        f"Emolumentos: {fmt_kz(factura.emolumentos)} KZ\n"
        f"Desp. Operacionais: {fmt_kz(factura.despesas_operacionais)} KZ\n"
        f"IVA ({factura_iva_pct}%): {fmt_kz(factura.iva)} KZ\n"
        f"Retenção: {fmt_kz(factura.retencao)} KZ\n"
        f"TOTAL: {fmt_kz(factura.valor_total)} KZ\n"
        f"\n--- DESPACHANTE ---\n"
        f"Nome: {responsavel_nome}\n"
        f"NIF: {responsavel_nif}\n"
        f"Cédula: {responsavel_cedula}\n"
    )
    import qrcode as _qr
    _qr_buf = io.BytesIO()
    _qr_obj = _qr.QRCode(version=1, box_size=10, border=2)
    _qr_obj.add_data(qr_data)
    _qr_obj.make(fit=True)
    _qr_obj.make_image(fill_color="black", back_color="white").save(_qr_buf, format='PNG')
    _qr_buf.seek(0)
    qr_flowable = RLImage(_qr_buf, width=1.9 * cm, height=1.9 * cm)

    top_line = Table([[
        col_logo, qr_flowable
    ]], colWidths=[W - 1.9 * cm, 1.9 * cm])
    top_line.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.insert(0, Spacer(1, 0.15 * cm))
    story.insert(0, top_line)

    # ── Subtítulo "Original"
    story.append(Paragraph('<b>Original</b>', st('orig', fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER,
                                                  textColor=COR_PRIMARIO)))
    story.append(Spacer(1, 0.15 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 5 — Tabela de itens (Ref | Descrição | Tipo | Valor)
    # ══════════════════════════════════════════════════════════════════════════
    # Cabeçalho
    ITENS_HEADER = [
        Paragraph('Ref.', s_th),
        Paragraph('Descrição', s_th),
        Paragraph('Tipo', s_th),
        Paragraph('Valor (KZ)', s_th),
    ]
    cw = [1.2*cm, W - 1.2*cm - 4.0*cm - 3.0*cm, 4.0*cm, 3.0*cm]

    ITENS = [ITENS_HEADER]
    total_geral_itens = Decimal('0')

    # Adicionar linha CIF
    v_cif_val = factura.requisicao_fundo.valor_cif if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo and factura.requisicao_fundo.valor_cif else (processo.valor_cif if processo and processo.valor_cif else Decimal('0'))
    if v_cif_val and v_cif_val > 0:
        ITENS.append([
            Paragraph('CIF', s_td_cent),
            Paragraph(merc[:50] if merc else 'Mercadoria', s_td),
            Paragraph('Valor CIF', s_td),
            Paragraph(fmt_kz(v_cif_val), s_td_right),
        ])

    # Listar cada linha da requisição individualmente
    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        # Despesas documentadas
        despesas_doc = factura.requisicao_fundo.linhas.filter(documentada=True)
        for idx, linha in enumerate(despesas_doc, start=1):
            v = linha.valor or Decimal('0')
            if not v or v <= 0:
                continue
            ITENS.append([
                Paragraph(f'EP{idx:02d}', s_td_cent),
                Paragraph(linha.despesa_tipo or 'Despesa', s_td),
                Paragraph('Direito (documentado)', s_td),
                Paragraph(fmt_kz(v), s_td_right),
            ])
            total_geral_itens += v

        # Despesas não documentadas
        despesas_nao_doc = factura.requisicao_fundo.linhas.filter(documentada=False)
        for idx, linha in enumerate(despesas_nao_doc, start=1):
            v = linha.valor or Decimal('0')
            if not v or v <= 0:
                continue
            ITENS.append([
                Paragraph(f'DE{idx:02d}', s_td_cent),
                Paragraph(linha.despesa_tipo or 'Despesa', s_td),
                Paragraph('Despesa (não documentada)', s_td),
                Paragraph(fmt_kz(v), s_td_right),
            ])
            total_geral_itens += v

    # Se não tem requisição vinculada, usar os valores directos da factura
    if total_geral_itens == 0:
        if factura.honorarios_despachante and factura.honorarios_despachante > 0:
            ITENS.append([
                Paragraph('01', s_td_cent),
                Paragraph('Honorários do Despachante', s_td),
                Paragraph('Honorários', s_td),
                Paragraph(fmt_kz(factura.honorarios_despachante), s_td_right),
            ])
            total_geral_itens += factura.honorarios_despachante
        if factura.taxas_aduaneiras and factura.taxas_aduaneiras > 0:
            ITENS.append([
                Paragraph('02', s_td_cent),
                Paragraph('Impostos e Taxas Aduaneiras', s_td),
                Paragraph('Taxas Aduaneiras', s_td),
                Paragraph(fmt_kz(factura.taxas_aduaneiras), s_td_right),
            ])
            total_geral_itens += factura.taxas_aduaneiras
        if factura.emolumentos and factura.emolumentos > 0:
            ITENS.append([
                Paragraph('03', s_td_cent),
                Paragraph('Emolumentos Gerais', s_td),
                Paragraph('Emolumentos', s_td),
                Paragraph(fmt_kz(factura.emolumentos), s_td_right),
            ])
            total_geral_itens += factura.emolumentos
        if factura.despesas_operacionais and factura.despesas_operacionais > 0:
            ITENS.append([
                Paragraph('04', s_td_cent),
                Paragraph('Despesas Operacionais', s_td),
                Paragraph('Despesas Operacionais', s_td),
                Paragraph(fmt_kz(factura.despesas_operacionais), s_td_right),
            ])
            total_geral_itens += factura.despesas_operacionais
        if factura.outros_encargos and factura.outros_encargos > 0:
            ITENS.append([
                Paragraph('05', s_td_cent),
                Paragraph('Outros Encargos', s_td),
                Paragraph('Outros', s_td),
                Paragraph(fmt_kz(factura.outros_encargos), s_td_right),
            ])
            total_geral_itens += factura.outros_encargos

    # Linhas em branco para preencher o espaço (mínimo 5 linhas)
    while len(ITENS) < 6:
        ITENS.append(['', '', '', ''])

    t_itens = Table(ITENS, colWidths=cw, repeatRows=1)
    t_itens.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), COR_HEADER),
        ('TEXTCOLOR',     (0, 0), (-1, 0), COR_PRIMARIO),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 7),
        ('ALIGN',         (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, 0), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, 0), 4),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
        ('FONTNAME',      (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1), (-1, -1), 8),
        ('GRID',          (0, 0), (-1, -1), 0.3, COR_BORDA),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [colors.white, COR_CLARO]),
        ('VALIGN',        (0, 1), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 5),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
    ]))
    story.append(t_itens)
    story.append(Spacer(1, 0.08 * cm))

    # ── Nota de bens
    nota_box = Table([[
        Paragraph('<font size="7" color="#475569"><i>Bens foram colocados à disposição do adquirente a data do documento</i></font>',
                  s_small)
    ]], colWidths=[W])
    nota_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), COR_CLARO),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.3, COR_BORDA),
    ]))
    story.append(nota_box)
    story.append(Spacer(1, 0.1 * cm))

    # Totais por categoria (para secção de totalizadores)
    taxas_total = Decimal('0')
    emol_total = Decimal('0')
    oper_total = Decimal('0')
    honor_total = Decimal('0')
    outros_total = Decimal('0')

    if hasattr(factura, 'requisicao_fundo') and factura.requisicao_fundo:
        for linha in factura.requisicao_fundo.linhas.all():
            v = linha.valor or Decimal('0')
            if not v or v <= 0:
                continue
            tc = (linha.tipo_custo or '').strip()
            dt = (linha.despesa_tipo or '').strip()
            if tc == 'Honorários do Despachante' or dt.startswith('Honorário'):
                honor_total += v
            elif tc == 'Impostos e Taxas Aduaneiras (AGT)':
                taxas_total += v
            elif tc == 'Despesas Portuárias e Terminais':
                emol_total += v
            elif tc in ('Logística e Transporte', 'Outros') or not tc:
                oper_total += v
            else:
                outros_total += v
    else:
        taxas_total = factura.taxas_aduaneiras or Decimal('0')
        emol_total = factura.emolumentos or Decimal('0')
        oper_total = factura.despesas_operacionais or Decimal('0')
        honor_total = factura.honorarios_despachante or Decimal('0')
        outros_total = factura.outros_encargos or Decimal('0')

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 6 — Resumo IVA (esquerda) + Totalizadores (direita)
    # ══════════════════════════════════════════════════════════════════════════
    iva_header = [
        Paragraph('<b>Resumo IVA</b>', st('iva_t', fontSize=8, fontName='Helvetica-Bold', textColor=COR_PRIMARIO)),
        '', '', ''
    ]
    iva_sub = [
        Paragraph('<b>Cód. IVA</b>', s_th),
        Paragraph('<b>Incidência</b>', s_th),
        Paragraph('<b>%IVA</b>', s_th),
        Paragraph('<b>Valor Motivo</b>', s_th),
    ]
    iva_rows = [
        iva_header,
        iva_sub,
        [f'{factura_iva_pct}%',
         Paragraph(fmt_kz(factura.honorarios_despachante), s_td_right),
         Paragraph(f'{factura_iva_pct:.2f}'.replace('.', ','), s_td_right),
         Paragraph(f'{fmt_kz(factura.iva)} IVA', s_td)],
        ['', Paragraph('<b>0,00</b>', s_td_right), Paragraph('<b>0,00</b>', s_td_right), ''],
    ]
    t_iva = Table(iva_rows, colWidths=[1.4*cm, 2.0*cm, 1.2*cm, W*0.35 - 4.6*cm])
    t_iva.setStyle(TableStyle([
        ('SPAN',          (0, 0), (-1, 0)),
        ('BACKGROUND',    (0, 0), (-1, 0), COR_HEADER),
        ('BACKGROUND',    (0, 1), (-1, 1), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR',     (0, 0), (-1, 1), COR_PRIMARIO),
        ('GRID',          (0, 1), (-1, -1), 0.3, COR_BORDA),
        ('BOX',           (0, 0), (-1, -1), 0.5, COR_BORDA),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('ALIGN',         (0, 2), (2, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    # Totalizadores direita
    def _tot_row(label, valor, bold=False, big=False):
        fn = 'Helvetica-Bold' if bold else 'Helvetica'
        fs = 10 if big else 8
        tc = COR_PRIMARIO if bold else COR_PRIMARIO
        return [
            Paragraph(f'<font size="{fs}" name="{fn}">{label}</font>',
                       st(f'tot_{label}', fontSize=fs, fontName=fn, alignment=TA_LEFT, textColor=tc)),
            Paragraph(f'<font size="{fs}" name="{fn}">{valor}</font>',
                       st(f'totv_{label}', fontSize=fs, fontName=fn, alignment=TA_RIGHT, textColor=tc)),
        ]

    tot_rows = [
        _tot_row('Mercadorias',  fmt_kz(taxas_total + emol_total + oper_total + outros_total)),
        _tot_row('Serviços',     fmt_kz(honor_total)),
        _tot_row('Outros',       fmt_kz(factura.outros_encargos)),
        _tot_row('IEC',          '0,00'),
        _tot_row('Retenção',     fmt_kz(factura.retencao) if factura.retencao > 0 else '0,00'),
        _tot_row('Nota Crédito', f'-{fmt_kz(factura.ajuste_nota_credito)}' if factura.ajuste_nota_credito > 0 else '0,00'),
        _tot_row('Nota Débito',  f'+{fmt_kz(factura.ajuste_nota_debito)}' if factura.ajuste_nota_debito > 0 else '0,00'),
        _tot_row(f'Total IVA ({factura_iva_pct:.0f}%)',    fmt_kz(factura.iva)),
        [Paragraph(f'<font size="10" name="Helvetica-Bold"><b>Total (AKZ):</b></font>',
                    st('tot_final', fontSize=10, fontName='Helvetica-Bold', textColor=COR_PRIMARIO)),
         Paragraph(f'<font size="10" name="Helvetica-Bold" color="#0f172a"><b>{fmt_kz(factura.valor_total)}</b></font>',
                    st('totv_final', fontSize=10, fontName='Helvetica-Bold', alignment=TA_RIGHT, textColor=COR_PRIMARIO))],
    ]

    t_tot = Table(tot_rows, colWidths=[W * 0.35, W * 0.2])
    t_tot.setStyle(TableStyle([
        ('GRID',          (0, 0), (-1, -2), 0.3, COR_BORDA),
        ('LINEABOVE',     (0, 7), (-1, 7), 1.5, COR_CINZA),
        ('BACKGROUND',    (0, 7), (-1, 7), COR_CLARO),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

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
    story.append(Spacer(1, 0.08 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 7 — Assinatura + Operador
    # ══════════════════════════════════════════════════════════════════════════
    _ass_img_fact = _carregar_assinatura(banca.usuario_id if banca else None)
    if _ass_img_fact:
        t_ass = Table([[
            '',
            Table([
                [_ass_img_fact],
                [Paragraph('<font size="7.5"><b>Assinatura do Despachante</b></font>',
                            st('ass', fontSize=7.5, alignment=TA_CENTER, fontName='Helvetica-Bold'))],
                [Spacer(1, 0.08*cm)],
                [Paragraph(f'<font size="7.5"><b>Operador:</b> {factura.criado_por_nome or "—"}</font>',
                            st('op', fontSize=7.5, alignment=TA_CENTER))],
            ], colWidths=[4.5*cm]),
        ]], colWidths=[W - 4.5*cm, 4.5*cm])
    else:
        t_ass = Table([[
            '',
            Table([
                [HRFlowable(width=4.5*cm, thickness=0.5, color=COR_BORDA)],
                [Paragraph('<font size="7.5"><b>Assinatura do Despachante</b></font>',
                            st('ass', fontSize=7.5, alignment=TA_CENTER, fontName='Helvetica-Bold'))],
                [Spacer(1, 0.15*cm)],
                [HRFlowable(width=4.5*cm, thickness=0.5, color=COR_BORDA)],
                [Paragraph(f'<font size="7.5"><b>Operador:</b> {factura.criado_por_nome or "—"}</font>',
                            st('op', fontSize=7.5, alignment=TA_CENTER))],
            ], colWidths=[4.5*cm]),
        ]], colWidths=[W - 4.5*cm, 4.5*cm])
    t_ass.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN',  (1, 0), (1, 0),  'CENTER'),
    ]))
    story.append(t_ass)

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO 8 — Dados Bancários (rodapé compacto)
    # ══════════════════════════════════════════════════════════════════════════
    bancos_pdf = []
    if banca:
        try:
            bancos_pdf = json.loads(banca.dados_bancarios_json or '[]')
        except (json.JSONDecodeError, ValueError):
            bancos_pdf = []
        if not isinstance(bancos_pdf, list):
            bancos_pdf = []

    has_bank_data = False
    if bancos_pdf:
        has_bank_data = any(b.get('banco') for b in bancos_pdf if isinstance(b, dict))
    elif banca:
        has_bank_data = bool(banca.banco or banca.numero_conta or banca.iban)

    if has_bank_data or (banca and banca.instrucoes_pagamento):
        story.append(Spacer(1, 0.06 * cm))
        story.append(HRFlowable(width=W, thickness=0.3, color=COR_BORDA))
        story.append(Spacer(1, 0.04 * cm))

        story.append(Paragraph(
            '<font size="5.5" color="#1e293b"><b>Dados Bancários</b></font>',
            st('bank_title', fontSize=5.5)
        ))

        if bancos_pdf:
            bank_lines = []
            for i, b in enumerate(bancos_pdf):
                if not isinstance(b, dict) or not b.get('banco'):
                    continue
                iban = b.get('iban', '—')
                bank_lines.append(
                    f'<font size="5" color="#475569">'
                    f'<b>{i + 1}.</b> <b>{b["banco"]}</b> IBAN: <font name="Courier">{iban}</font>'
                    f'</font>'
                )
            story.append(Paragraph(
                ' &nbsp;&nbsp; '.join(bank_lines),
                st('bank_all', fontSize=5, leading=7, leftIndent=8)
            ))
        elif banca:
            parts = []
            if banca.banco:
                parts.append(f'<b>Banco:</b> {banca.banco}')
            if banca.iban:
                parts.append(f'<b>IBAN:</b> <font name="Courier">{banca.iban}</font>')
            if banca.numero_conta:
                parts.append(f'<b>Conta:</b> {banca.numero_conta}')
            if parts:
                story.append(Paragraph(
                    f'<font size="5" color="#475569">{" &nbsp;|&nbsp; ".join(parts)}</font>',
                    st('bank_foot', fontSize=5, leading=6.5, leftIndent=8)
                ))

        if banca and banca.instrucoes_pagamento:
            texto_pagamento = banca.instrucoes_pagamento.replace('\n', ' ').replace('\r', '')
            story.append(Paragraph(
                f'<font size="5" color="#64748b"><i>{texto_pagamento}</i></font>',
                st('bank_inst', fontSize=5, leading=6.5, leftIndent=8)
            ))

    # ══════════════════════════════════════════════════════════════════════════
    # CONSTRUIR E RETORNAR
    # ══════════════════════════════════════════════════════════════════════════
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Factura_{factura.numero_factura}.pdf"'
    return response

@safe_pdf
@requer_sessao_ativa
def recibo_pdf(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    banca = recibo.banca
    cliente = recibo.cliente
    buffer = io.BytesIO()

    s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))

    dd_h = [
        Paragraph('<b>Nº Recibo</b>', s), Paragraph('<b>Factura</b>', s),
        Paragraph('<b>Forma Pgto</b>', s), Paragraph('<b>Data Pgto</b>', s),
        Paragraph('<b>Referência</b>', s),
    ]
    dd_v = [
        Paragraph(recibo.numero_recibo, s), Paragraph(recibo.factura.numero_factura, s),
        Paragraph(recibo.forma_pagamento, s),
        Paragraph(recibo.data_pagamento.strftime('%d/%m/%Y') if recibo.data_pagamento else '—', s),
        Paragraph(recibo.referencia_bancaria or 'N/D', s),
    ]

    colunas = ['Descrição', 'Valor Recebido (KZ)']
    linhas = [
        [f'Pagamento da Factura {recibo.factura.numero_factura}', fmt_kz(recibo.valor_recebido)]
    ]

    sumario = [
        ('Valor Recebido', f'{fmt_kz(recibo.valor_recebido)} KZ'),
        ('Estado', 'PAGO'),
        ('Emitido Por', recibo.utilizador_responsavel_nome),
    ]

    qr_texto = (
        "=== RECIBO DE PAGAMENTO ===\n"
        f"No: {recibo.numero_recibo}\n"
        f"Data: {recibo.data_pagamento.strftime('%d/%m/%Y')}\n"
        f"Estado: PAGO\n"
        f"--- CLIENTE ---\n"
        f"Nome: {cliente.nome}\n"
        f"NIF: {cliente.nif}\n"
        f"--- PAGAMENTO ---\n"
        f"Factura: {recibo.factura.numero_factura}\n"
        f"Valor: {fmt_kz(recibo.valor_recebido)} KZ\n"
        f"Forma: {recibo.forma_pagamento}\n"
        f"Referencia: {recibo.referencia_bancaria or 'N/D'}\n"
        f"--- DESPACHANTE ---\n"
        f"Nome: {banca.nome}\n"
        f"NIF: {banca.nif}\n"
        f"Emitido Por: {recibo.utilizador_responsavel_nome}"
    )

    _construir_pdf_documento(
        buffer, f"Recibo de Pagamento {recibo.numero_recibo}",
        "Documento Comprovativo de Pagamento", banca, cliente,
        recibo.numero_recibo,
        recibo.data_pagamento or recibo.data_criacao.date() if hasattr(recibo, 'data_criacao') else None,
        dados_doc_header=dd_h, dados_doc_valores=dd_v,
        tabela_colunas=colunas, tabela_linhas=linhas,
        sumario_linhas=sumario, total_geral=recibo.valor_recebido,
        nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
        qr_flowable=_gerar_qr_code_flowable(qr_texto),
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="Recibo_{recibo.numero_recibo}.pdf"'
    return response


@safe_pdf
@requer_sessao_ativa
def factura_recibo_pdf(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    banca = fr.banca
    cliente = fr.cliente
    buffer = io.BytesIO()

    s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))

    dd_h = [
        Paragraph('<b>Nº Factura-Recibo</b>', s), Paragraph('<b>Data</b>', s),
        Paragraph('<b>Forma Pgto</b>', s), Paragraph('<b>Estado</b>', s),
        Paragraph('<b>Emitido Por</b>', s),
    ]
    dd_v = [
        Paragraph(fr.numero_factura_recibo, s),
        Paragraph(fr.data.strftime('%d/%m/%Y') if fr.data else '—', s),
        Paragraph(fr.forma_pagamento, s), Paragraph(fr.estado, s),
        Paragraph(fr.utilizador_responsavel_nome, s),
    ]

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
        colunas = ['Descrição', 'Valor Pago (KZ)']
        linhas = [['Prestação de Serviços de Despacho com pagamento imediato', fmt_kz(fr.valor)]]

    sumario = [
        ('Valor Pago', f'{fmt_kz(fr.valor)} KZ'),
        ('Forma de Pagamento', fr.forma_pagamento),
        ('Estado', fr.estado),
    ]

    qr_texto = (
        "=== FACTURA-RECIBO ===\n"
        f"No: {fr.numero_factura_recibo}\n"
        f"Data: {fr.data.strftime('%d/%m/%Y')}\n"
        f"Estado: {fr.estado}\n"
        f"--- CLIENTE ---\n"
        f"Nome: {cliente.nome}\n"
        f"NIF: {cliente.nif}\n"
        f"--- VALORES ---\n"
        f"Factura: {fr.factura.numero_factura if fr.factura_id else 'N/D'}\n"
        f"Valor: {fmt_kz(fr.valor)} KZ\n"
        f"Forma: {fr.forma_pagamento}\n"
        f"--- DESPACHANTE ---\n"
        f"Nome: {banca.nome}\n"
        f"NIF: {banca.nif}\n"
        f"Emitido Por: {fr.utilizador_responsavel_nome}"
    )

    _construir_pdf_documento(
        buffer, f"Factura-Recibo {fr.numero_factura_recibo}",
        "Venda a Pronto Pagamento", banca, cliente,
        fr.numero_factura_recibo, fr.data,
        dados_doc_header=dd_h, dados_doc_valores=dd_v,
        tabela_colunas=colunas, tabela_linhas=linhas,
        sumario_linhas=sumario, total_geral=fr.valor,
        nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
        qr_flowable=_gerar_qr_code_flowable(qr_texto),
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="FacturaRecibo_{fr.numero_factura_recibo}.pdf"'
    return response


@safe_pdf
@requer_sessao_ativa
def nota_credito_pdf(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    banca = nota.banca
    cliente = nota.cliente
    buffer = io.BytesIO()

    s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))

    dd_h = [
        Paragraph('<b>Nº Nota</b>', s), Paragraph('<b>Factura</b>', s),
        Paragraph('<b>Data</b>', s), Paragraph('<b>Estado</b>', s),
        Paragraph('<b>Motivo</b>', s),
    ]
    dd_v = [
        Paragraph(nota.numero_nota, s),
        Paragraph(nota.factura_relacionada.numero_factura, s),
        Paragraph(nota.data.strftime('%d/%m/%Y') if nota.data else '—', s),
        Paragraph(nota.estado, s),
        Paragraph(nota.motivo[:60], s),
    ]

    colunas = ['Descrição', 'Valor Creditado (KZ)']
    linhas = [
        [f'Crédito referente à Factura {nota.factura_relacionada.numero_factura}',
         fmt_kz(nota.valor_creditado)]
    ]

    sumario = [
        ('Valor Creditado', f'{fmt_kz(nota.valor_creditado)} KZ'),
        ('Estado', nota.estado),
        ('Criado Por', nota.utilizador_criador_nome),
        ('Aprovado Por', nota.utilizador_aprovador_nome or 'N/D'),
    ]

    qr_texto = (
        "=== NOTA DE CREDITO ===\n"
        f"No: {nota.numero_nota}\n"
        f"Data: {nota.data.strftime('%d/%m/%Y')}\n"
        f"Estado: {nota.estado}\n"
        f"--- CLIENTE ---\n"
        f"Nome: {cliente.nome}\n"
        f"NIF: {cliente.nif}\n"
        f"--- DETALHES ---\n"
        f"Factura: {nota.factura_relacionada.numero_factura}\n"
        f"Valor: {fmt_kz(nota.valor_creditado)} KZ\n"
        f"Motivo: {nota.motivo}\n"
        f"--- DESPACHANTE ---\n"
        f"Nome: {banca.nome}\n"
        f"NIF: {banca.nif}\n"
        f"Criado Por: {nota.utilizador_criador_nome}\n"
        f"Aprovado Por: {nota.utilizador_aprovador_nome or 'N/D'}"
    )

    _construir_pdf_documento(
        buffer, f"Nota de Crédito {nota.numero_nota}",
        "Documento de Retificação de Facturação", banca, cliente,
        nota.numero_nota, nota.data,
        dados_doc_header=dd_h, dados_doc_valores=dd_v,
        tabela_colunas=colunas, tabela_linhas=linhas,
        sumario_linhas=sumario, total_geral=nota.valor_creditado,
        nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
        qr_flowable=_gerar_qr_code_flowable(qr_texto),
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NotaCredito_{nota.numero_nota}.pdf"'
    return response


@safe_pdf
@requer_sessao_ativa
def nota_debito_pdf(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    banca = nota.banca
    cliente = nota.cliente
    buffer = io.BytesIO()

    s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))

    dd_h = [
        Paragraph('<b>Nº Nota</b>', s), Paragraph('<b>Factura</b>', s),
        Paragraph('<b>Data</b>', s), Paragraph('<b>Estado</b>', s),
        Paragraph('<b>Motivo</b>', s),
    ]
    dd_v = [
        Paragraph(nota.numero_nota, s),
        Paragraph(nota.factura_relacionada.numero_factura, s),
        Paragraph(nota.data.strftime('%d/%m/%Y') if nota.data else '—', s),
        Paragraph(nota.estado, s),
        Paragraph(nota.motivo[:60], s),
    ]

    colunas = ['Descrição', 'Valor Debitado (KZ)']
    linhas = [
        [f'Débito adicional referente à Factura {nota.factura_relacionada.numero_factura}',
         fmt_kz(nota.valor)]
    ]

    sumario = [
        ('Valor Debitado', f'{fmt_kz(nota.valor)} KZ'),
        ('Estado', nota.estado),
        ('Criado Por', nota.utilizador_criador_nome),
    ]

    qr_texto = (
        "=== NOTA DE DEBITO ===\n"
        f"No: {nota.numero_nota}\n"
        f"Data: {nota.data.strftime('%d/%m/%Y')}\n"
        f"Estado: {nota.estado}\n"
        f"--- CLIENTE ---\n"
        f"Nome: {cliente.nome}\n"
        f"NIF: {cliente.nif}\n"
        f"--- DETALHES ---\n"
        f"Factura: {nota.factura_relacionada.numero_factura}\n"
        f"Valor: {fmt_kz(nota.valor)} KZ\n"
        f"Motivo: {nota.motivo}\n"
        f"--- DESPACHANTE ---\n"
        f"Nome: {banca.nome}\n"
        f"NIF: {banca.nif}\n"
        f"Criado Por: {nota.utilizador_criador_nome}"
    )

    _construir_pdf_documento(
        buffer, f"Nota de Débito {nota.numero_nota}",
        "Documento de Encargo Adicional", banca, cliente,
        nota.numero_nota, nota.data,
        dados_doc_header=dd_h, dados_doc_valores=dd_v,
        tabela_colunas=colunas, tabela_linhas=linhas,
        sumario_linhas=sumario, total_geral=nota.valor,
        nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
        qr_flowable=_gerar_qr_code_flowable(qr_texto),
    )

    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="NotaDebito_{nota.numero_nota}.pdf"'
    return response


# ═══ Envio por Email ═════════════════════════════════════════════════════════

@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def recibo_enviar_email(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    cliente = recibo.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        banca = recibo.banca
        s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))
        dd_h = [
            Paragraph('<b>Nº Recibo</b>', s), Paragraph('<b>Factura</b>', s),
            Paragraph('<b>Forma Pgto</b>', s), Paragraph('<b>Data Pgto</b>', s),
            Paragraph('<b>Referência</b>', s),
        ]
        dd_v = [
            Paragraph(recibo.numero_recibo, s), Paragraph(recibo.factura.numero_factura, s),
            Paragraph(recibo.forma_pagamento, s),
            Paragraph(recibo.data_pagamento.strftime('%d/%m/%Y') if recibo.data_pagamento else '—', s),
            Paragraph(recibo.referencia_bancaria or 'N/D', s),
        ]
        colunas = ['Descrição', 'Valor Recebido (KZ)']
        linhas = [[f'Pagamento da Factura {recibo.factura.numero_factura}', fmt_kz(recibo.valor_recebido)]]
        sumario = [('Valor Recebido', f'{fmt_kz(recibo.valor_recebido)} KZ'), ('Estado', 'PAGO'), ('Emitido Por', recibo.utilizador_responsavel_nome)]
        qr_texto = (
            "=== RECIBO DE PAGAMENTO ===\n"
            f"No: {recibo.numero_recibo}\n"
            f"Data: {recibo.data_pagamento.strftime('%d/%m/%Y')}\n"
            f"Estado: PAGO\n"
            f"--- CLIENTE ---\n"
            f"Nome: {recibo.cliente.nome}\n"
            f"NIF: {recibo.cliente.nif}\n"
            f"--- PAGAMENTO ---\n"
            f"Factura: {recibo.factura.numero_factura}\n"
            f"Valor: {fmt_kz(recibo.valor_recebido)} KZ\n"
            f"Forma: {recibo.forma_pagamento}\n"
            f"Referencia: {recibo.referencia_bancaria or 'N/D'}\n"
            f"--- DESPACHANTE ---\n"
            f"Nome: {banca.nome}\n"
            f"NIF: {banca.nif}\n"
            f"Emitido Por: {recibo.utilizador_responsavel_nome}"
        )
        _construir_pdf_documento(
            buffer, f"Recibo de Pagamento {recibo.numero_recibo}",
            "Documento Comprovativo de Pagamento", banca, cliente,
            recibo.numero_recibo,
            recibo.data_pagamento or recibo.data_criacao.date() if hasattr(recibo, 'data_criacao') else None,
            dados_doc_header=dd_h, dados_doc_valores=dd_v,
            tabela_colunas=colunas, tabela_linhas=linhas,
            sumario_linhas=sumario, total_geral=recibo.valor_recebido,
            nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
            qr_flowable=_gerar_qr_code_flowable(qr_texto),
        )
        buffer.seek(0)
        anexos = [(f'Recibo_{recibo.numero_recibo}.pdf', buffer.read(), 'application/pdf')]
        
        assunto = f"Recibo de Pagamento {recibo.numero_recibo} – SICDOA"
        
        texto = f"""Prezado(a) {cliente.nome},
        
Confirmamos a recepção do seu pagamento no valor de {fmt_kz(recibo.valor_recebido)} KZ.

Detalhes do Recibo:
  Número: {recibo.numero_recibo}
  Factura: {recibo.factura.numero_factura}
  Forma de Pagamento: {recibo.forma_pagamento}
  Data do Pagamento: {recibo.data_pagamento.strftime('%d/%m/%Y')}
  Referência: {recibo.referencia_bancaria or 'N/D'}

Agradecemos a sua preferência.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Confirmação de Pagamento</h2>
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
            <p>Confirmamos a recepção do seu pagamento com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número do Recibo:</td>
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
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Referência Bancária:</td>
                    <td style="padding: 10px;">{recibo.referencia_bancaria or 'N/D'}</td>
                </tr>
            </table>
            <p style="margin-top: 25px;">Agradecemos a sua preferência.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Recibo {recibo.numero_recibo} enviado por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

    return redirect('financeiro:recibo_detalhe', pk=pk)

@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def factura_recibo_enviar_email(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    cliente = fr.cliente

    if fr.estado == 'Cancelada':
        messages.error(request, 'Não é possível enviar email de uma Factura-Recibo cancelada.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        banca = fr.banca
        s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))
        dd_h = [
            Paragraph('<b>Nº Factura-Recibo</b>', s), Paragraph('<b>Data</b>', s),
            Paragraph('<b>Forma Pgto</b>', s), Paragraph('<b>Estado</b>', s),
            Paragraph('<b>Emitido Por</b>', s),
        ]
        dd_v = [
            Paragraph(fr.numero_factura_recibo, s),
            Paragraph(fr.data.strftime('%d/%m/%Y') if fr.data else '—', s),
            Paragraph(fr.forma_pagamento, s), Paragraph(fr.estado, s),
            Paragraph(fr.utilizador_responsavel_nome, s),
        ]
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
            colunas = ['Descrição', 'Valor Pago (KZ)']
            linhas = [['Prestação de Serviços de Despacho com pagamento imediato', fmt_kz(fr.valor)]]
        sumario = [('Valor Pago', f'{fmt_kz(fr.valor)} KZ'), ('Forma de Pagamento', fr.forma_pagamento), ('Estado', fr.estado)]
        qr_texto = (
            "=== FACTURA-RECIBO ===\n"
            f"No: {fr.numero_factura_recibo}\n"
            f"Data: {fr.data.strftime('%d/%m/%Y')}\n"
            f"Estado: {fr.estado}\n"
            f"--- CLIENTE ---\n"
            f"Nome: {fr.cliente.nome}\n"
            f"NIF: {fr.cliente.nif}\n"
            f"--- VALORES ---\n"
            f"Factura: {fr.factura.numero_factura if fr.factura_id else 'N/D'}\n"
            f"Valor: {fmt_kz(fr.valor)} KZ\n"
            f"Forma: {fr.forma_pagamento}\n"
            f"--- DESPACHANTE ---\n"
            f"Nome: {banca.nome}\n"
            f"NIF: {banca.nif}\n"
            f"Emitido Por: {fr.utilizador_responsavel_nome}"
        )
        _construir_pdf_documento(
            buffer, f"Factura-Recibo {fr.numero_factura_recibo}",
            "Venda a Pronto Pagamento", banca, cliente,
            fr.numero_factura_recibo, fr.data,
            dados_doc_header=dd_h, dados_doc_valores=dd_v,
            tabela_colunas=colunas, tabela_linhas=linhas,
            sumario_linhas=sumario, total_geral=fr.valor,
            nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
            qr_flowable=_gerar_qr_code_flowable(qr_texto),
        )
        buffer.seek(0)
        anexos = [(f'FacturaRecibo_{fr.numero_factura_recibo}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Factura-Recibo {fr.numero_factura_recibo} – SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Factura-Recibo referente à prestação de serviços de despacho.

Detalhes:
  Número: {fr.numero_factura_recibo}
  Valor: {fmt_kz(fr.valor)} KZ
  Forma de Pagamento: {fr.forma_pagamento}
  Data: {fr.data.strftime('%d/%m/%Y')}

Agradecemos a sua preferência.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Factura-Recibo – Confirmação de Pagamento</h2>
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
            <p>Segue em anexo a Factura-Recibo com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
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
            <p style="margin-top: 25px;">Agradecemos a sua preferência.</p>
            <p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p>
        </body>
        </html>
        """

        _enviar(assunto, texto, html, cliente.email, anexos=anexos)
        messages.success(request, f'Factura-Recibo {fr.numero_factura_recibo} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

    return redirect('financeiro:factura_recibo_detalhe', pk=pk)


# ═══ Envio por Email – Notas de Crédito e Débito ════════════════════════════

@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def nota_credito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        banca = nota.banca
        s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))
        dd_h = [
            Paragraph('<b>Nº Nota</b>', s), Paragraph('<b>Factura</b>', s),
            Paragraph('<b>Data</b>', s), Paragraph('<b>Estado</b>', s),
            Paragraph('<b>Motivo</b>', s),
        ]
        dd_v = [
            Paragraph(nota.numero_nota, s),
            Paragraph(nota.factura_relacionada.numero_factura, s),
            Paragraph(nota.data.strftime('%d/%m/%Y') if nota.data else '—', s),
            Paragraph(nota.estado, s),
            Paragraph(nota.motivo[:60], s),
        ]
        colunas = ['Descrição', 'Valor Creditado (KZ)']
        linhas = [[f'Crédito referente à Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor_creditado)]]
        sumario = [('Valor Creditado', f'{fmt_kz(nota.valor_creditado)} KZ'), ('Estado', nota.estado), ('Criado Por', nota.utilizador_criador_nome), ('Aprovado Por', nota.utilizador_aprovador_nome or 'N/D')]
        qr_texto = (
            "=== NOTA DE CREDITO ===\n"
            f"No: {nota.numero_nota}\n"
            f"Data: {nota.data.strftime('%d/%m/%Y')}\n"
            f"Estado: {nota.estado}\n"
            f"--- CLIENTE ---\n"
            f"Nome: {nota.cliente.nome}\n"
            f"NIF: {nota.cliente.nif}\n"
            f"--- DETALHES ---\n"
            f"Factura: {nota.factura_relacionada.numero_factura}\n"
            f"Valor: {fmt_kz(nota.valor_creditado)} KZ\n"
            f"Motivo: {nota.motivo}\n"
            f"--- DESPACHANTE ---\n"
            f"Nome: {banca.nome}\n"
            f"NIF: {banca.nif}\n"
            f"Criado Por: {nota.utilizador_criador_nome}\n"
            f"Aprovado Por: {nota.utilizador_aprovador_nome or 'N/D'}"
        )
        _construir_pdf_documento(
            buffer, f"Nota de Crédito {nota.numero_nota}",
            "Documento de Retificação de Facturação", banca, cliente,
            nota.numero_nota, nota.data,
            dados_doc_header=dd_h, dados_doc_valores=dd_v,
            tabela_colunas=colunas, tabela_linhas=linhas,
            sumario_linhas=sumario, total_geral=nota.valor_creditado,
            nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
            qr_flowable=_gerar_qr_code_flowable(qr_texto),
        )
        buffer.seek(0)
        anexos = [(f'NotaCredito_{nota.numero_nota}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Nota de Crédito {nota.numero_nota} – SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de Crédito referente à factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  Número: {nota.numero_nota}
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
            <h2 style="color: #137fec;">Nota de Crédito</h2>
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
            <p>Segue em anexo a Nota de Crédito com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
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
                    <td style="padding: 10px;">{_safe(nota.motivo)}</td>
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
        messages.success(request, f'Nota de Crédito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@require_POST
@requer_sessao_ativa
@requer_escrita_financeira
def nota_debito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        buffer = io.BytesIO()
        banca = nota.banca
        s = ParagraphStyle('x', fontSize=7.5, fontName='Helvetica', textColor=colors.HexColor('#0f172a'))
        dd_h = [
            Paragraph('<b>Nº Nota</b>', s), Paragraph('<b>Factura</b>', s),
            Paragraph('<b>Data</b>', s), Paragraph('<b>Estado</b>', s),
            Paragraph('<b>Motivo</b>', s),
        ]
        dd_v = [
            Paragraph(nota.numero_nota, s),
            Paragraph(nota.factura_relacionada.numero_factura, s),
            Paragraph(nota.data.strftime('%d/%m/%Y') if nota.data else '—', s),
            Paragraph(nota.estado, s),
            Paragraph(nota.motivo[:60], s),
        ]
        colunas = ['Descrição', 'Valor Debitado (KZ)']
        linhas = [[f'Débito adicional referente à Factura {nota.factura_relacionada.numero_factura}', fmt_kz(nota.valor)]]
        sumario = [('Valor Debitado', f'{fmt_kz(nota.valor)} KZ'), ('Estado', nota.estado), ('Criado Por', nota.utilizador_criador_nome)]
        qr_texto = (
            "=== NOTA DE DEBITO ===\n"
            f"No: {nota.numero_nota}\n"
            f"Data: {nota.data.strftime('%d/%m/%Y')}\n"
            f"Estado: {nota.estado}\n"
            f"--- CLIENTE ---\n"
            f"Nome: {nota.cliente.nome}\n"
            f"NIF: {nota.cliente.nif}\n"
            f"--- DETALHES ---\n"
            f"Factura: {nota.factura_relacionada.numero_factura}\n"
            f"Valor: {fmt_kz(nota.valor)} KZ\n"
            f"Motivo: {nota.motivo}\n"
            f"--- DESPACHANTE ---\n"
            f"Nome: {banca.nome}\n"
            f"NIF: {banca.nif}\n"
            f"Criado Por: {nota.utilizador_criador_nome}"
        )
        _construir_pdf_documento(
            buffer, f"Nota de Débito {nota.numero_nota}",
            "Documento de Encargo Adicional", banca, cliente,
            nota.numero_nota, nota.data,
            dados_doc_header=dd_h, dados_doc_valores=dd_v,
            tabela_colunas=colunas, tabela_linhas=linhas,
            sumario_linhas=sumario, total_geral=nota.valor,
            nota_texto='Os originais das contas referidas vão devidamente selecionadas pelo valor dos honorários.',
            qr_flowable=_gerar_qr_code_flowable(qr_texto),
        )
        buffer.seek(0)
        anexos = [(f'NotaDebito_{nota.numero_nota}.pdf', buffer.read(), 'application/pdf')]

        assunto = f"Nota de Débito {nota.numero_nota} – SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de Débito referente à factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  Número: {nota.numero_nota}
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
            <h2 style="color: #137fec;">Nota de Débito</h2>
            <p>Prezado(a) <strong>{_safe(cliente.nome)}</strong>,</p>
            <p>Segue em anexo a Nota de Débito com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
                    <td style="padding: 10px;">{nota.numero_nota}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Factura Relacionada:</td>
                    <td style="padding: 10px;">{nota.factura_relacionada.numero_factura}</td>
                </tr>
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Debitado:</td>
                    <td style="padding: 10px; font-weight: bold; color: #1a1a1a;">{fmt_kz(nota.valor)} KZ</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Motivo:</td>
                    <td style="padding: 10px;">{_safe(nota.motivo)}</td>
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
        messages.success(request, f'Nota de Débito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, 'Erro ao enviar e-mail. Tente novamente mais tarde.')

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
        return JsonResponse({'success': False, 'error': 'Erro interno. Tente novamente.'})


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
        return JsonResponse({'success': False, 'error': 'Erro interno. Tente novamente.'})


@requer_sessao_ativa
@require_http_methods(["GET"])
def api_buscar_cliente(request):
    """API: Busca clientes por NIF ou nome para autocomplete"""
    try:
        q = request.GET.get('q', '').strip()
        if len(q) < 1:
            qs = Cliente.objects.filter(ativo=True)
            usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
            if usuario_id and not _user_tem_acesso_total(request):
                qs = qs.filter(usuario_id=usuario_id)
            qs = qs.order_by('nome')[:20]
            clientes = [
                {'value': c.id, 'label': f'{c.nif} - {c.nome}', 'nome': c.nome, 'nif': c.nif}
                for c in qs
            ]
            return JsonResponse({'success': True, 'clientes': clientes})

        qs = Cliente.objects.filter(ativo=True)
        usuario_id = request.session.get('banca_usuario_id') or request.session.get('usuario_id')
        if usuario_id and not _user_tem_acesso_total(request):
            qs = qs.filter(usuario_id=usuario_id)

        from django.db.models import Q
        qs = qs.filter(
            Q(nif__icontains=q) | Q(nome__icontains=q)
        ).order_by('nome')[:20]

        clientes = [
            {'value': c.id, 'label': f'{c.nif} - {c.nome}', 'nome': c.nome, 'nif': c.nif}
            for c in qs
        ]
        return JsonResponse({'success': True, 'clientes': clientes})
    except Exception as e:
        logger.exception("Erro ao buscar clientes")
        return JsonResponse({'success': False, 'error': 'Erro interno.'})


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
        filtro = {}
        if cliente.nif:
            filtro['nif_declarante__iexact'] = cliente.nif
        else:
            filtro['exportador_nome__iexact'] = cliente.nome
        filtro['status'] = 'Submetida'
        
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
        logger.exception("Erro ao carregar processos")
        return JsonResponse({
            'success': False, 
            'error': 'Erro ao carregar processos.'
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
                    'numero_bl_awb': _ad('documento_precedente'),  # DU: Documento Precedente (Campo 40, 1ª adição)
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
        logger.exception("Erro ao carregar dados")
        return JsonResponse({'success': False, 'error': 'Erro ao carregar dados.'})


@requer_sessao_ativa
@require_http_methods(["GET"])
def api_facturas_por_cliente(request):
    """API: Retorna facturas de um cliente para filtrar dropdown de NC/ND"""
    try:
        cliente_id = request.GET.get('cliente_id')
        if not cliente_id:
            return JsonResponse({'success': True, 'facturas': []})

        try:
            cliente_id = int(cliente_id)
        except (ValueError, TypeError):
            return JsonResponse({'success': True, 'facturas': []})

        facturas = (
            FacturaCliente.objects
            .filter(cliente_id=cliente_id)
            .exclude(estado='Cancelada')
            .order_by('-data_emissao')
            .values('id', 'numero_factura', 'valor_total', 'estado')
        )
        return JsonResponse({
            'success': True,
            'facturas': list(facturas)
        })

    except Exception as e:
        logger.exception("Erro ao buscar facturas por cliente")
        return JsonResponse({'success': False, 'error': 'Erro ao carregar facturas.'})

