import json
import io
from django.core.serializers.json import DjangoJSONEncoder
from django.views.generic import ListView, CreateView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q

from django.conf import settings

from users.auth_decorators import requer_sessao_ativa
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica
from .models import RequisicaoFundo, FacturaCliente, ReciboCliente, NotaCredito, NotaDebito, FacturaRecibo, HistoricoFinanceiro, registrar_historico
from .forms import (
    RequisicaoFundoForm, FacturaClienteForm, ReciboClienteForm, 
    NotaCreditoForm, NotaDebitoForm, FacturaReciboForm
)

class BaseContextMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.session.get('usuario'):
            context['usuario'] = self.request.session['usuario']
            context['papel'] = self.request.session['usuario'].get('papel', '')
            context['nome'] = self.request.session['usuario'].get('nome', '')
        return context

    def _get_user_cliente_filter(self):
        papel = self.request.session.get('usuario', {}).get('papel', '')
        if papel in ('Administrador', 'Gestor Financeiro'):
            return {}
        usuario_id = self.request.session.get('usuario_id')
        if not usuario_id:
            return {}
        return {'cliente__usuario_id': usuario_id}

    def _get_user_filter_direct(self):
        papel = self.request.session.get('usuario', {}).get('papel', '')
        if papel in ('Administrador', 'Gestor Financeiro'):
            return {}
        usuario_id = self.request.session.get('usuario_id')
        if not usuario_id:
            return {}
        return {'usuario_id': usuario_id}

    def _get_user_requisicao_filter(self):
        papel = self.request.session.get('usuario', {}).get('papel', '')
        if papel in ('Administrador', 'Gestor Financeiro'):
            return {}
        usuario_id = self.request.session.get('usuario_id')
        if not usuario_id:
            return {}
        return Q(cliente__usuario_id=usuario_id) | Q(solicitante_id=usuario_id)

# ─── Notas Home ─────────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/notas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'notas'
        return context


# ─── Facturas Home ──────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturasHomeView(BaseContextMixin, TemplateView):
    template_name = 'financeiro/facturas_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas'
        return context


# ─── DU → Factura Consolidation ────────────────────────────────────────────

@requer_sessao_ativa
def du_custos_json(request, pk):
    du = get_object_or_404(DeclaracaoUnica, pk=pk)
    data = {
        'taxas_aduaneiras': float((du.total_impostos or 0)),
        'emolumentos': float((du.emolumentos or 0) + (du.total_emgead or 0)),
        'iva': float(du.iva or 0),
    }
    return JsonResponse(data)


def _get_object_or_404_com_scope(request, model, pk, scope_field='cliente__usuario_id'):
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel in ('Administrador', 'Gestor Financeiro'):
        return get_object_or_404(model, pk=pk)
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return get_object_or_404(model, pk=pk)
    return get_object_or_404(model, **{scope_field: usuario_id, 'pk': pk})

# ─── Requisições de Fundos ───────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class RequisicaoFundoListView(BaseContextMixin, ListView):
    model = RequisicaoFundo
    template_name = 'financeiro/requisicao_fundo_lista.html'
    context_object_name = 'requisicoes'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
        filtro = self._get_user_requisicao_filter()
        if filtro:
            qs = qs.filter(filtro)
        busca = self.request.GET.get('busca')
        if busca:
            qs = qs.filter(numero_requisicao__icontains=busca) | qs.filter(cliente__nome__icontains=busca)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['busca'] = self.request.GET.get('busca', '')
        context['total_requisicoes'] = self.get_queryset().count()
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class RequisicaoFundoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = RequisicaoFundo
    form_class = RequisicaoFundoForm
    template_name = 'financeiro/requisicao_fundo_form.html'
    success_url = reverse_lazy('financeiro:requisicao_lista')
    success_message = "Requisição de fundos criada com sucesso!"

    def dispatch(self, request, *args, **kwargs):
        papel = request.session.get('usuario', {}).get('papel', '')
        if papel in ('Administrador', 'Gestor Financeiro'):
            messages.error(request, 'Apenas Despachantes podem criar requisições de fundos.')
            return redirect('financeiro:requisicao_lista')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.solicitante_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.solicitante_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'Requisicao', self.object.pk, self.object.numero_requisicao, 'Criada',
            estado_novo='Pendente', valor=self.object.valor_solicitado,
            utilizador_id=self.object.solicitante_id, utilizador_nome=self.object.solicitante_nome,
            cliente_nome=self.object.cliente.nome,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Requisição de Fundos"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        clientes_qs = Cliente.objects.filter(ativo=True)
        filtro_cliente = self._get_user_filter_direct()
        if filtro_cliente:
            clientes_qs = clientes_qs.filter(**filtro_cliente)
        context['clientes_json'] = json.dumps(list(clientes_qs.values('id', 'nif', 'nome')))
        context['processos_json'] = json.dumps(list(DeclaracaoUnica.objects.values('id', 'nif_declarante', 'numero_du')))
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class RequisicaoFundoDetailView(BaseContextMixin, DetailView):
    model = RequisicaoFundo
    template_name = 'financeiro/requisicao_fundo_detalhe.html'
    context_object_name = 'requisicao'

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        filtro = self._get_user_requisicao_filter()
        if filtro:
            queryset = queryset.filter(filtro)
        obj = get_object_or_404(queryset, pk=self.kwargs.get('pk'))
        papel = self.request.session.get('usuario', {}).get('papel', '')
        if obj.estado == 'Pendente' and papel in ('Administrador', 'Gestor Financeiro'):
            obj.estado = 'Em Aprovação'
            obj.save(update_fields=['estado'])
            obj.refresh_from_db()
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'requisicoes'
        context['historico'] = HistoricoFinanceiro.objects.filter(
            tipo_documento='Requisicao', documento_id=self.object.pk
        )[:20]
        return context

@requer_sessao_ativa
def aprovar_requisicao(request, pk):
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel not in ('Administrador', 'Gestor Financeiro'):
        messages.error(request, 'Apenas o Administrador ou o Gestor Financeiro podem aprovar requisições.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    requisicao = get_object_or_404(RequisicaoFundo, pk=pk)
    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Aprovada'
        requisicao.responsavel_aprovacao_id_usuario = request.session.get('usuario_id')
        usuario_data = request.session.get('usuario', {})
        requisicao.responsavel_aprovacao_nome = usuario_data.get('nome', '')
        requisicao.save()
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Aprovada',
            estado_anterior=estado_anterior, estado_novo='Aprovada', valor=requisicao.valor_solicitado,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
        )
        messages.success(request, f'Requisição {requisicao.numero_requisicao} aprovada com sucesso.')

        # Notificar solicitante por email
        if requisicao.solicitante_id:
            try:
                from users.models import Usuario
                from utils.email_utils import _enviar
                solicitante = Usuario.objects.get(id=requisicao.solicitante_id)
                if solicitante.email:
                    assunto = f"Requisição {requisicao.numero_requisicao} Aprovada — SICDOA"
                    texto = (
                        f"Prezado(a) {solicitante.nome},\n\n"
                        f"A sua requisição de fundos {requisicao.numero_requisicao} "
                        f"no valor de {requisicao.valor_solicitado:,.2f} Kz foi APROVADA.\n\n"
                        f"Cliente: {requisicao.cliente.nome}\n"
                        f"Justificação: {requisicao.justificacao}\n"
                        f"Aprovado por: {usuario_data.get('nome', '')}\n\n"
                        f"Atenciosamente,\nEquipa SICDOA"
                    )
                    html = (
                        f"<html><body style='font-family:Arial;padding:20px;'>"
                        f"<h2 style='color:#16a34a;'>Requisição Aprovada</h2>"
                        f"<p>Prezado(a) <strong>{solicitante.nome}</strong>,</p>"
                        f"<p>A sua requisição foi <strong style='color:#16a34a;'>APROVADA</strong>.</p>"
                        f"<table style='border-collapse:collapse;width:100%;max-width:500px;'>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Nº Requisição:</td><td>{requisicao.numero_requisicao}</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Valor:</td><td>{requisicao.valor_solicitado:,.2f} Kz</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Cliente:</td><td>{requisicao.cliente.nome}</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Aprovado por:</td><td>{usuario_data.get('nome', '')}</td></tr>"
                        f"</table><br><p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p></body></html>"
                    )
                    _enviar(assunto, texto, html, solicitante.email)
            except Exception:
                pass
    return redirect('financeiro:requisicao_detalhe', pk=pk)

@requer_sessao_ativa
def rejeitar_requisicao(request, pk):
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel not in ('Administrador', 'Gestor Financeiro'):
        messages.error(request, 'Apenas o Administrador ou o Gestor Financeiro podem rejeitar requisições.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    requisicao = get_object_or_404(RequisicaoFundo, pk=pk)
    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Rejeitada'
        requisicao.responsavel_aprovacao_id_usuario = request.session.get('usuario_id')
        usuario_data = request.session.get('usuario', {})
        requisicao.responsavel_aprovacao_nome = usuario_data.get('nome', '')
        requisicao.save()
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Rejeitada',
            estado_anterior=estado_anterior, estado_novo='Rejeitada', valor=requisicao.valor_solicitado,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
        )
        messages.warning(request, f'Requisição {requisicao.numero_requisicao} foi rejeitada.')

        # Notificar solicitante por email
        if requisicao.solicitante_id:
            try:
                from users.models import Usuario
                from utils.email_utils import _enviar
                solicitante = Usuario.objects.get(id=requisicao.solicitante_id)
                if solicitante.email:
                    assunto = f"Requisição {requisicao.numero_requisicao} Rejeitada — SICDOA"
                    texto = (
                        f"Prezado(a) {solicitante.nome},\n\n"
                        f"A sua requisição de fundos {requisicao.numero_requisicao} "
                        f"no valor de {requisicao.valor_solicitado:,.2f} Kz foi REJEITADA.\n\n"
                        f"Cliente: {requisicao.cliente.nome}\n"
                        f"Justificação: {requisicao.justificacao}\n"
                        f"Rejeitado por: {usuario_data.get('nome', '')}\n\n"
                        f"Atenciosamente,\nEquipa SICDOA"
                    )
                    html = (
                        f"<html><body style='font-family:Arial;padding:20px;'>"
                        f"<h2 style='color:#dc2626;'>Requisição Rejeitada</h2>"
                        f"<p>Prezado(a) <strong>{solicitante.nome}</strong>,</p>"
                        f"<p>A sua requisição foi <strong style='color:#dc2626;'>REJEITADA</strong>.</p>"
                        f"<table style='border-collapse:collapse;width:100%;max-width:500px;'>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Nº Requisição:</td><td>{requisicao.numero_requisicao}</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Valor:</td><td>{requisicao.valor_solicitado:,.2f} Kz</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Cliente:</td><td>{requisicao.cliente.nome}</td></tr>"
                        f"<tr><td style='padding:8px;font-weight:bold;'>Rejeitado por:</td><td>{usuario_data.get('nome', '')}</td></tr>"
                        f"</table><br><p>Atenciosamente,<br><strong>Equipa SICDOA</strong></p></body></html>"
                    )
                    _enviar(assunto, texto, html, solicitante.email)
            except Exception:
                pass
    return redirect('financeiro:requisicao_detalhe', pk=pk)

@requer_sessao_ativa
def cancelar_requisicao(request, pk):
    requisicao = _get_object_or_404_com_scope(request, RequisicaoFundo, pk)
    if requisicao.estado not in ('Pendente', 'Em Aprovação'):
        messages.error(request, 'Apenas requisições pendentes ou em aprovação podem ser canceladas.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        papel == 'Administrador' or
        requisicao.solicitante_id == usuario_id
    )
    if not pode_cancelar:
        messages.error(request, 'Apenas o solicitante ou o Administrador podem cancelar esta requisição.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = requisicao.estado
        requisicao.estado = 'Cancelada'
        requisicao.save()
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'Requisicao', requisicao.pk, requisicao.numero_requisicao, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=requisicao.valor_solicitado,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=requisicao.cliente.nome,
        )
        messages.success(request, f'Requisição {requisicao.numero_requisicao} cancelada com sucesso.')
    return redirect('financeiro:requisicao_detalhe', pk=pk)

@requer_sessao_ativa
def eliminar_requisicao(request, pk):
    requisicao = get_object_or_404(RequisicaoFundo, pk=pk)
    papel = request.session.get('usuario', {}).get('papel', '')
    if papel != 'Administrador':
        messages.error(request, 'Apenas o Administrador pode eliminar requisições.')
        return redirect('financeiro:requisicao_detalhe', pk=pk)

    if request.method == 'POST':
        numero = requisicao.numero_requisicao
        requisicao.delete()
        messages.success(request, f'Requisição {numero} eliminada permanentemente.')
        return redirect('financeiro:requisicao_lista')

    return redirect('financeiro:requisicao_detalhe', pk=pk)


# ─── Facturas Finais ─────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaClienteListView(BaseContextMixin, ListView):
    model = FacturaCliente
    template_name = 'financeiro/factura_lista.html'
    context_object_name = 'facturas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
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

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaClienteCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = FacturaCliente
    form_class = FacturaClienteForm
    template_name = 'financeiro/factura_form.html'
    success_url = reverse_lazy('financeiro:factura_lista')
    success_message = "Factura Final criada com sucesso!"

    def form_valid(self, form):
        form.instance.criado_por_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.criado_por_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'Factura', self.object.pk, self.object.numero_factura, 'Criada',
            estado_novo=self.object.estado, valor=self.object.valor_total,
            utilizador_id=self.object.criado_por_id, utilizador_nome=self.object.criado_por_nome,
            cliente_nome=self.object.cliente.nome,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Factura Final"
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

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaClienteDetailView(BaseContextMixin, DetailView):
    model = FacturaCliente
    template_name = 'financeiro/factura_detalhe.html'
    context_object_name = 'factura'

    def get_queryset(self):
        qs = super().get_queryset()
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


# ─── Gestão de Recibos ───────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class ReciboClienteListView(BaseContextMixin, ListView):
    model = ReciboCliente
    template_name = 'financeiro/recibo_lista.html'
    context_object_name = 'recibos'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
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
        response = super().form_valid(form)
        registrar_historico(
            'Recibo', self.object.pk, self.object.numero_recibo, 'Criado',
            estado_novo='Pago', valor=self.object.valor_recebido,
            utilizador_id=self.object.utilizador_responsavel_id, utilizador_nome=self.object.utilizador_responsavel_nome,
            cliente_nome=self.object.cliente.nome,
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
        qs = super().get_queryset()
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


# ─── Notas de Crédito ────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaCreditoListView(BaseContextMixin, ListView):
    model = NotaCredito
    template_name = 'financeiro/nota_credito_lista.html'
    context_object_name = 'notas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
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
class NotaCreditoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = NotaCredito
    form_class = NotaCreditoForm
    template_name = 'financeiro/nota_credito_form.html'
    success_url = reverse_lazy('financeiro:nota_credito_lista')
    success_message = "Nota de Crédito emitida com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'NotaCredito', self.object.pk, self.object.numero_nota, 'Criada',
            estado_novo='Pendente', valor=self.object.valor_creditado,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
        )
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
        qs = super().get_queryset()
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

@requer_sessao_ativa
def aprovar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_aprovar = (
        papel in ('Administrador', 'Gestor Financeiro') or
        nota.utilizador_criador_id == usuario_id
    )
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
        )
        messages.success(request, f'Nota de Crédito {nota.numero_nota} aprovada e creditada na conta corrente do cliente.')

        # Envio automático de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de Crédito {nota.numero_nota} aprovada — SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de Crédito {nota.numero_nota} foi aprovada no valor de {nota.valor_creditado:,.2f} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                pass
    return redirect('financeiro:nota_credito_detalhe', pk=pk)

@requer_sessao_ativa
def rejeitar_nota_credito(request, pk):
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    pode_rejeitar = (
        papel in ('Administrador', 'Gestor Financeiro') or
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
        )
        messages.warning(request, f'Nota de Crédito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@requer_sessao_ativa
def cancelar_nota_credito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    if nota.estado not in ('Pendente',):
        messages.error(request, 'Apenas notas de crédito pendentes podem ser canceladas.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        papel == 'Administrador' or
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
        )
        messages.success(request, f'Nota de Crédito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_credito_detalhe', pk=pk)


# ─── Notas de Débito ─────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class NotaDebitoListView(BaseContextMixin, ListView):
    model = NotaDebito
    template_name = 'financeiro/nota_debito_lista.html'
    context_object_name = 'notas'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
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
class NotaDebitoCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = NotaDebito
    form_class = NotaDebitoForm
    template_name = 'financeiro/nota_debito_form.html'
    success_url = reverse_lazy('financeiro:nota_debito_lista')
    success_message = "Nota de Débito emitida com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_criador_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_criador_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'NotaDebito', self.object.pk, self.object.numero_nota, 'Criada',
            estado_novo='Pendente', valor=self.object.valor,
            utilizador_id=self.object.utilizador_criador_id, utilizador_nome=self.object.utilizador_criador_nome,
            cliente_nome=self.object.cliente.nome,
        )
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
        qs = super().get_queryset()
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


@requer_sessao_ativa
def aprovar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_aprovar = (
        papel in ('Administrador', 'Gestor Financeiro') or
        nota.utilizador_criador_id == usuario_id
    )
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
        )
        messages.success(request, f'Nota de Débito {nota.numero_nota} aprovada e debitada na conta corrente do cliente.')

        # Envio automático de email ao cliente
        if nota.cliente.email:
            try:
                from utils.email_utils import _enviar
                assunto = f"Nota de Débito {nota.numero_nota} aprovada — SICDOA"
                texto = (
                    f"Prezado(a) {nota.cliente.nome},\n\n"
                    f"A Nota de Débito {nota.numero_nota} foi aprovada no valor de {nota.valor:,.2f} Kz.\n"
                    f"Motivo: {nota.motivo}\n\n"
                    f"Atenciosamente,\nEquipa SICDOA"
                )
                _enviar(assunto, texto, '', nota.cliente.email)
            except Exception:
                pass
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@requer_sessao_ativa
def rejeitar_nota_debito(request, pk):
    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    pode_rejeitar = (
        papel in ('Administrador', 'Gestor Financeiro') or
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
        )
        messages.warning(request, f'Nota de Débito {nota.numero_nota} rejeitada.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


@requer_sessao_ativa
def cancelar_nota_debito(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    if nota.estado not in ('Pendente',):
        messages.error(request, 'Apenas notas de débito pendentes podem ser canceladas.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    usuario_id = request.session.get('usuario_id')
    papel = request.session.get('usuario', {}).get('papel', '')
    pode_cancelar = (
        papel == 'Administrador' or
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
        )
        messages.success(request, f'Nota de Débito {nota.numero_nota} cancelada com sucesso.')
    return redirect('financeiro:nota_debito_detalhe', pk=pk)


# ─── Facturas-Recibo ─────────────────────────────────────────────────────────

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaReciboListView(BaseContextMixin, ListView):
    model = FacturaRecibo
    template_name = 'financeiro/factura_recibo_lista.html'
    context_object_name = 'facturas_recibo'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset()
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

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaReciboCreateView(BaseContextMixin, SuccessMessageMixin, CreateView):
    model = FacturaRecibo
    form_class = FacturaReciboForm
    template_name = 'financeiro/factura_recibo_form.html'
    success_url = reverse_lazy('financeiro:factura_recibo_lista')
    success_message = "Factura-Recibo emitida com sucesso!"

    def form_valid(self, form):
        form.instance.utilizador_responsavel_id = self.request.session.get('usuario_id')
        usuario_data = self.request.session.get('usuario', {})
        form.instance.utilizador_responsavel_nome = usuario_data.get('nome', '')
        response = super().form_valid(form)
        registrar_historico(
            'FacturaRecibo', self.object.pk, self.object.numero_factura_recibo, 'Criada',
            estado_novo='Paga', valor=self.object.valor,
            utilizador_id=self.object.utilizador_responsavel_id, utilizador_nome=self.object.utilizador_responsavel_nome,
            cliente_nome=self.object.cliente.nome,
        )
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo'] = "Nova Factura-Recibo"
        context['active_menu'] = 'Financeiro'
        context['active_sub'] = 'facturas_recibo'
        return context

@method_decorator(requer_sessao_ativa, name='dispatch')
class FacturaReciboDetailView(BaseContextMixin, DetailView):
    model = FacturaRecibo
    template_name = 'financeiro/factura_recibo_detalhe.html'
    context_object_name = 'factura_recibo'

    def get_queryset(self):
        qs = super().get_queryset()
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
def cancelar_factura_recibo(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    if fr.estado != 'Paga':
        messages.error(request, 'Apenas facturas-recibo com estado "Paga" podem ser canceladas.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    if request.method == 'POST':
        estado_anterior = fr.estado
        fr.estado = 'Cancelada'
        fr.save(update_fields=['estado'])
        usuario_data = request.session.get('usuario', {})
        registrar_historico(
            'FacturaRecibo', fr.pk, fr.numero_factura_recibo, 'Cancelada',
            estado_anterior=estado_anterior, estado_novo='Cancelada', valor=fr.valor,
            utilizador_id=request.session.get('usuario_id'), utilizador_nome=usuario_data.get('nome', ''),
            cliente_nome=fr.cliente.nome,
        )
        messages.success(request, f'Factura-Recibo {fr.numero_factura_recibo} cancelada com sucesso.')
    return redirect('financeiro:factura_recibo_detalhe', pk=pk)


# ─── Geração de PDFs ─────────────────────────────────────────────────────────

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

    # Cabeçalho
    header_data = [[
        Paragraph(titulo.upper(), s_titulo),
        Paragraph(f'<b>{info_geral}</b>', ParagraphStyle('st', fontSize=10, fontName='Helvetica-Bold', alignment=2, textColor=cor_primaria))
    ]]
    t_header = Table(header_data, colWidths=[W - 5.5*cm, 5.5*cm])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(t_header)
    story.append(Paragraph(subtitulo, s_subtitulo))
    story.append(HRFlowable(width=W, thickness=2, color=cor_primaria, spaceAfter=12))

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
        Paragraph(f'<b>{total_geral:,.2f} KZ</b>', ParagraphStyle('tv', fontSize=11, fontName='Helvetica-Bold', textColor=colors.white, alignment=2)),
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
    story.append(Paragraph('Assinatura do Responsável', ParagraphStyle('ass', fontSize=8, fontName='Helvetica', alignment=1)))

    doc.build(story)

@requer_sessao_ativa
def factura_pdf(request, pk):
    factura = _get_object_or_404_com_scope(request, FacturaCliente, pk)
    buffer = io.BytesIO()
    
    dados_kv = [
        ('NIF do Cliente', factura.cliente.nif),
        ('Nome do Cliente', factura.cliente.nome),
        ('Processo Aduaneiro', factura.processo_aduaneiro.numero_du if factura.processo_aduaneiro else 'N/D'),
        ('Data de Emissão', factura.data_emissao.strftime('%d/%m/%Y %H:%M')),
        ('Data de Vencimento', factura.data_vencimento.strftime('%d/%m/%Y')),
        ('Estado', factura.estado),
        ('Emitido Por', factura.criado_por_nome),
        ('Descrição', factura.descricao),
    ]

    colunas = ['Descrição do Item / Encargo', 'Valor (KZ)']
    linhas = [
        ['Honorários do Despachante', f'{factura.honorarios_despachante:,.2f}'],
        ['Taxas Aduaneiras', f'{factura.taxas_aduaneiras:,.2f}'],
        ['Emolumentos', f'{factura.emolumentos:,.2f}'],
        ['Despesas Operacionais', f'{factura.despesas_operacionais:,.2f}'],
        ['IVA', f'{factura.iva:,.2f}'],
        ['Outros Encargos', f'{factura.outros_encargos:,.2f}'],
    ]

    _construir_pdf_base(
        buffer, 
        f"Factura Final {factura.numero_factura}",
        f"Documento de Cobrança de Despacho Aduaneiro",
        factura.estado,
        dados_kv,
        colunas,
        linhas,
        factura.valor_total
    )
    
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
    ]

    colunas = ['Conceito', 'Valor Recebido (KZ)']
    linhas = [
        [f'Pagamento da Factura {recibo.factura.numero_factura}', f'{recibo.valor_recebido:,.2f}']
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
        [f'Crédito referente à Factura {nota.factura_relacionada.numero_factura}', f'{nota.valor_creditado:,.2f}']
    ]

    _construir_pdf_base(
        buffer, 
        f"Nota de Crédito {nota.numero_nota}",
        f"Documento de Retificação de Faturação",
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
        ('Criado Por', nota.utilizador_criador_nome),
    ]

    colunas = ['Conceito', 'Valor Debitado (KZ)']
    linhas = [
        [f'Débito adicional referente à Factura {nota.factura_relacionada.numero_factura}', f'{nota.valor:,.2f}']
    ]

    _construir_pdf_base(
        buffer, 
        f"Nota de Débito {nota.numero_nota}",
        f"Documento de Encargo Adicional",
        "EMITIDA",
        dados_kv,
        colunas,
        linhas,
        nota.valor
    )

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

    colunas = ['Descrição / Venda Direta', 'Valor Pago (KZ)']
    linhas = [
        ['Prestação de Serviços de Despacho com pagamento imediato', f'{fr.valor:,.2f}']
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


# ─── Envio por Email ─────────────────────────────────────────────────────────

@requer_sessao_ativa
def recibo_enviar_email(request, pk):
    recibo = _get_object_or_404_com_scope(request, ReciboCliente, pk)
    cliente = recibo.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar
        
        assunto = f"Recibo de Pagamento {recibo.numero_recibo} — SICDOA"
        
        texto = f"""Prezado(a) {cliente.nome},
        
Confirmamos a recepção do seu pagamento no valor de {recibo.valor_recebido:,.2f} KZ.

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
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
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
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{recibo.valor_recebido:,.2f} KZ</td>
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

        _enviar(assunto, texto, html, cliente.email)
        messages.success(request, f'Recibo {recibo.numero_recibo} enviado por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:recibo_detalhe', pk=pk)

@requer_sessao_ativa
def factura_recibo_enviar_email(request, pk):
    fr = _get_object_or_404_com_scope(request, FacturaRecibo, pk)
    cliente = fr.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:factura_recibo_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        assunto = f"Factura-Recibo {fr.numero_factura_recibo} — SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Factura-Recibo referente à prestação de serviços de despacho.

Detalhes:
  Número: {fr.numero_factura_recibo}
  Valor: {fr.valor:,.2f} KZ
  Forma de Pagamento: {fr.forma_pagamento}
  Data: {fr.data.strftime('%d/%m/%Y')}

Agradecemos a sua preferência.

Atenciosamente,
Equipa SICDOA
"""

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #137fec;">Factura-Recibo — Confirmação de Pagamento</h2>
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
            <p>Segue em anexo a Factura-Recibo com os seguintes detalhes:</p>
            <table style="width: 100%; max-width: 600px; border-collapse: collapse; margin-top: 15px;">
                <tr style="background-color: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Número:</td>
                    <td style="padding: 10px;">{fr.numero_factura_recibo}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px; font-weight: bold; color: #475569;">Valor Pago:</td>
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{fr.valor:,.2f} KZ</td>
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

        _enviar(assunto, texto, html, cliente.email)
        messages.success(request, f'Factura-Recibo {fr.numero_factura_recibo} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:factura_recibo_detalhe', pk=pk)


# ─── Envio por Email — Notas de Crédito e Débito ────────────────────────────

@requer_sessao_ativa
def nota_credito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaCredito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:nota_credito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        assunto = f"Nota de Crédito {nota.numero_nota} — SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de Crédito referente à factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  Número: {nota.numero_nota}
  Factura Relacionada: {nota.factura_relacionada.numero_factura}
  Valor Creditado: {nota.valor_creditado:,.2f} KZ
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
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
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
                    <td style="padding: 10px; font-weight: bold; color: #137fec;">{nota.valor_creditado:,.2f} KZ</td>
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

        _enviar(assunto, texto, html, cliente.email)
        messages.success(request, f'Nota de Crédito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:nota_credito_detalhe', pk=pk)


@requer_sessao_ativa
def nota_debito_enviar_email(request, pk):
    nota = _get_object_or_404_com_scope(request, NotaDebito, pk)
    cliente = nota.cliente

    if not cliente.email:
        messages.error(request, f'O cliente {cliente.nome} não possui endereço de email configurado.')
        return redirect('financeiro:nota_debito_detalhe', pk=pk)

    try:
        from utils.email_utils import _enviar

        assunto = f"Nota de Débito {nota.numero_nota} — SICDOA"

        texto = f"""Prezado(a) {cliente.nome},

Segue em anexo a Nota de Débito referente à factura {nota.factura_relacionada.numero_factura}.

Detalhes:
  Número: {nota.numero_nota}
  Factura Relacionada: {nota.factura_relacionada.numero_factura}
  Valor Debitado: {nota.valor:,.2f} KZ
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
            <p>Prezado(a) <strong>{cliente.nome}</strong>,</p>
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
                    <td style="padding: 10px; font-weight: bold; color: #dc2626;">{nota.valor:,.2f} KZ</td>
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

        _enviar(assunto, texto, html, cliente.email)
        messages.success(request, f'Nota de Débito {nota.numero_nota} enviada por e-mail para {cliente.email} com sucesso.')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {str(e)}')

    return redirect('financeiro:nota_debito_detalhe', pk=pk)
