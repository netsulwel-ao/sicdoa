from django import forms
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica
from .models import (
    RequisicaoFundo, FluxoAprovacao, NivelAprovacao,
    FacturaCliente, ReciboCliente,
    NotaCredito, NotaDebito, FacturaRecibo
)


class FluxoAprovacaoForm(forms.ModelForm):
    class Meta:
        model = FluxoAprovacao
        fields = ['nome', 'descricao', 'ativo']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all',
                'placeholder': 'Ex: Fluxo Padrão'
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all resize-none',
                'rows': 3,
                'placeholder': 'Descrição do fluxo de aprovação...'
            }),
            'ativo': forms.CheckboxInput(attrs={
                'class': 'size-4 rounded border-gray-300 text-primary focus:ring-primary/30'
            }),
        }


class NivelAprovacaoForm(forms.ModelForm):
    class Meta:
        model = NivelAprovacao
        fields = ['nome', 'qtde_aprovadores', 'funcao']
        widgets = {
            'nome': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all',
                'placeholder': 'Ex: 1ª Aprovação'
            }),
            'qtde_aprovadores': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all',
                'min': 1,
                'placeholder': '1'
            }),
            'funcao': forms.Select(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border-2 border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all',
            }),
        }


class RequisicaoFundoForm(forms.ModelForm):
    class Meta:
        model = RequisicaoFundo
        fields = ['cliente', 'processo_aduaneiro', 'valor_solicitado', 'justificacao', 'documento_justificativo', 'fluxo_aprovacao']
        widgets = {
            'cliente': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'processo_aduaneiro': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'valor_solicitado': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': '0.00',
                'step': '0.01'
            }),
            'justificacao': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all resize-none',
                'rows': '4',
                'placeholder': 'Justifique o pedido de fundos...'
            }),
            'documento_justificativo': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 transition-all cursor-pointer'
            }),
            'fluxo_aprovacao': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fluxo_aprovacao'].queryset = FluxoAprovacao.objects.filter(ativo=True)
        self.fields['fluxo_aprovacao'].empty_label = None
        self.fields['fluxo_aprovacao'].required = True
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                nif = Cliente.objects.filter(id=cliente_id).values_list('nif', flat=True).first()
                if nif:
                    self.fields['processo_aduaneiro'].queryset = DeclaracaoUnica.objects.filter(
                        nif_declarante=nif
                    )
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        valor_solicitado = cleaned_data.get('valor_solicitado')
        processo_aduaneiro = cleaned_data.get('processo_aduaneiro')
        fluxo_aprovacao = cleaned_data.get('fluxo_aprovacao')
        if not fluxo_aprovacao:
            self.add_error('fluxo_aprovacao', 'Seleccione um Fluxo de Aprovação. A requisição não pode ser submetida sem um fluxo definido.')

        if cliente and processo_aduaneiro:
            nif_cliente = (cliente.nif or '').strip()
            nif_processo = (processo_aduaneiro.nif_declarante or '').strip()
            if nif_cliente and nif_processo and nif_cliente != nif_processo:
                self.add_error(
                    'processo_aduaneiro',
                    f'Atenção: O processo aduaneiro selecionado pertence ao NIF "{nif_processo}", '
                    f'mas o cliente escolhido tem o NIF "{nif_cliente}". '
                    'Selecione um processo que corresponda ao cliente.'
                )

        if cliente and valor_solicitado:
            if valor_solicitado <= 0:
                self.add_error('valor_solicitado', 'O valor solicitado deve ser maior que zero.')
                return cleaned_data

            from django.db.models import Sum
            requisicoes_ativas = RequisicaoFundo.objects.filter(
                cliente=cliente,
                estado__in=['Pendente', 'Em Aprovação', 'Aprovada']
            )
            if self.instance.pk:
                requisicoes_ativas = requisicoes_ativas.exclude(pk=self.instance.pk)

            total_comprometido = requisicoes_ativas.aggregate(total=Sum('valor_solicitado'))['total'] or 0
            novo_total = total_comprometido + valor_solicitado
            limite = cliente.limite_financeiro

            if limite == 0:
                self.add_error(
                    'cliente',
                    'Este cliente não tem um limite financeiro atribuído (Limite = 0). '
                    'Configure o limite de crédito do cliente antes de solicitar fundos.'
                )
            elif novo_total > limite:
                self.add_error(
                    'valor_solicitado',
                    f'Este valor ultrapassa o limite de crédito do cliente. '
                    f'Limite: {limite:,.2f} Kz | Comprometido: {total_comprometido:,.2f} Kz | '
                    f'Disponível: {(limite - total_comprometido):,.2f} Kz.'
                )

        return cleaned_data


class RequisicaoFundoUpdateForm(forms.ModelForm):
    class Meta:
        model = RequisicaoFundo
        fields = ['justificacao', 'documento_justificativo']
        widgets = {
            'justificacao': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all resize-none',
                'rows': '4',
                'placeholder': 'Justifique o pedido de fundos...'
            }),
            'documento_justificativo': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 transition-all cursor-pointer'
            }),
        }


class FacturaClienteForm(forms.ModelForm):
    class Meta:
        model = FacturaCliente
        fields = [
            'cliente', 'processo_aduaneiro', 'honorarios_despachante', 
            'taxas_aduaneiras', 'emolumentos', 'despesas_operacionais', 
            'iva', 'outros_encargos', 'data_vencimento', 'descricao'
        ]
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'processo_aduaneiro': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'honorarios_despachante': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'taxas_aduaneiras': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'emolumentos': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'despesas_operacionais': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'iva': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'outros_encargos': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'data_vencimento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
            'descricao': forms.Textarea(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm resize-none', 'rows': '3'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                nif = Cliente.objects.filter(id=cliente_id).values_list('nif', flat=True).first()
                if nif:
                    self.fields['processo_aduaneiro'].queryset = DeclaracaoUnica.objects.filter(
                        nif_declarante=nif
                    )
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        processo_aduaneiro = cleaned_data.get('processo_aduaneiro')

        if cliente and processo_aduaneiro:
            nif_cliente = (cliente.nif or '').strip()
            nif_processo = (processo_aduaneiro.nif_declarante or '').strip()
            if nif_cliente and nif_processo and nif_cliente != nif_processo:
                self.add_error(
                    'processo_aduaneiro',
                    f'Atenção: O processo aduaneiro selecionado pertence ao NIF "{nif_processo}", '
                    f'mas o cliente escolhido tem o NIF "{nif_cliente}".'
                )
        return cleaned_data


class ReciboClienteForm(forms.ModelForm):
    class Meta:
        model = ReciboCliente
        fields = ['cliente', 'factura', 'valor_recebido', 'forma_pagamento', 'data_pagamento', 'referencia_bancaria']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor_recebido': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
            'referencia_bancaria': forms.TextInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                self.fields['factura'].queryset = FacturaCliente.objects.filter(cliente_id=cliente_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        factura = cleaned_data.get('factura')
        valor_recebido = cleaned_data.get('valor_recebido')

        if factura and cliente and factura.cliente != cliente:
            self.add_error('factura', 'A factura selecionada não pertence ao cliente escolhido.')

        if factura and valor_recebido:
            if valor_recebido <= 0:
                self.add_error('valor_recebido', 'O valor deve ser superior a zero.')
            else:
                restante = factura.valor_total - factura.valor_pago
                if self.instance.pk:
                    restante += self.instance.valor_recebido
                if valor_recebido > restante:
                    self.add_error('valor_recebido', f'O valor recebido excede o valor pendente desta factura ({restante:,.2f} Kz).')

        return cleaned_data


class ReciboClienteUpdateForm(forms.ModelForm):
    class Meta:
        model = ReciboCliente
        fields = ['valor_recebido', 'forma_pagamento', 'data_pagamento', 'referencia_bancaria']
        widgets = {
            'valor_recebido': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
            'referencia_bancaria': forms.TextInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
        }


class NotaCreditoForm(forms.ModelForm):
    class Meta:
        model = NotaCredito
        fields = ['cliente', 'factura_relacionada', 'valor_creditado', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor_creditado': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'motivo': forms.Select(choices=[
                ('Erro de facturação', 'Erro de facturação'),
                ('Desconto posterior', 'Desconto posterior'),
                ('Devolução de valores', 'Devolução de valores'),
                ('Ajustes contabilísticos', 'Ajustes contabilísticos'),
            ], attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                self.fields['factura_relacionada'].queryset = FacturaCliente.objects.filter(cliente_id=cliente_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        factura_relacionada = cleaned_data.get('factura_relacionada')
        valor_creditado = cleaned_data.get('valor_creditado')

        if factura_relacionada and cliente and factura_relacionada.cliente != cliente:
            self.add_error('factura_relacionada', 'A factura selecionada não pertence ao cliente escolhido.')

        if factura_relacionada and valor_creditado:
            if valor_creditado <= 0:
                self.add_error('valor_creditado', 'O valor deve ser maior que zero.')
            elif valor_creditado > factura_relacionada.valor_total:
                self.add_error('valor_creditado', f'O valor a creditar não pode exceder o valor total da factura ({factura_relacionada.valor_total:,.2f} Kz).')

        return cleaned_data


class NotaDebitoForm(forms.ModelForm):
    class Meta:
        model = NotaDebito
        fields = ['cliente', 'factura_relacionada', 'valor', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'motivo': forms.Select(choices=[
                ('Taxas adicionais', 'Taxas adicionais'),
                ('Correções de valores', 'Correções de valores'),
                ('Encargos não considerados inicialmente', 'Encargos não considerados inicialmente'),
            ], attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                self.fields['factura_relacionada'].queryset = FacturaCliente.objects.filter(cliente_id=cliente_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        factura_relacionada = cleaned_data.get('factura_relacionada')
        valor = cleaned_data.get('valor')

        if factura_relacionada and cliente and factura_relacionada.cliente != cliente:
            self.add_error('factura_relacionada', 'A factura selecionada não pertence ao cliente escolhido.')

        if valor:
            if valor <= 0:
                self.add_error('valor', 'O valor deve ser maior que zero.')
            elif factura_relacionada and valor > factura_relacionada.valor_total:
                self.add_error('valor', f'O valor a debitar não pode exceder o valor total da factura ({factura_relacionada.valor_total:,.2f} Kz).')

        return cleaned_data


class FacturaReciboForm(forms.ModelForm):
    class Meta:
        model = FacturaRecibo
        fields = ['cliente', 'factura', 'valor', 'forma_pagamento', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor': forms.NumberInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'step': '0.01'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import FacturaCliente
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                self.fields['factura'].queryset = FacturaCliente.objects.filter(cliente_id=cliente_id, estado__in=['Pendente', 'Parcialmente Paga'])
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        valor = cleaned_data.get('valor')
        cliente = cleaned_data.get('cliente')
        factura = cleaned_data.get('factura')

        if factura and cliente and factura.cliente != cliente:
            self.add_error('factura', 'A factura selecionada não pertence ao cliente escolhido.')

        if valor and valor <= 0:
            self.add_error('valor', 'O valor deve ser maior que zero.')

        if factura and valor:
            restante = factura.valor_total - factura.valor_pago
            if valor > restante:
                self.add_error('valor', f'O valor excede o valor pendente desta factura ({restante:,.2f} Kz).')

        return cleaned_data
