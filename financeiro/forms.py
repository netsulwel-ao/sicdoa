from django import forms
from decimal import Decimal, InvalidOperation
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica
from utils.format_kz import fmt_kz, parse_kz
from .models import (
    FacturaCliente, ReciboCliente,
    NotaCredito, NotaDebito, FacturaRecibo,
    RequisicaoFundo, RequisicaoFundoLinha
)


class RequisicaoFundoForm(forms.ModelForm):
    class Meta:
        model = RequisicaoFundo
        fields = ['banca', 'filial', 'cliente', 'pessoa_contacto', 'processo_aduaneiro', 
                 'numero_bl_awb', 'meio_transporte', 'origem', 'destino', 'mercadoria_descricao',
                 'peso_bruto_kg', 'peso_liquido_kg', 'cbm_metros_cubicos', 'quantidade_volumes', 'valor_cif',
                 'data_validade', 'moeda_referencia', 'cambio_referencia', 'observacoes',
                 'banco', 'numero_conta', 'iban', 'instrucoes_envio']
        widgets = {
            'banca': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'filial': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'cliente': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'pessoa_contacto': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Nome da pessoa de contacto'
            }),
            'processo_aduaneiro': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'numero_bl_awb': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: BL123456 ou AWB1234567'
            }),
            'meio_transporte': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: Navio MSC - 2026 ou Voo TAP-100'
            }),
            'origem': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: Lisboa / Porto de Lisboa'
            }),
            'destino': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: Luanda / Porto de Luanda'
            }),
            'mercadoria_descricao': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all resize-none',
                'rows': '2',
                'placeholder': 'Descrição resumida da mercadoria'
            }),
            'peso_bruto_kg': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'peso_liquido_kg': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'cbm_metros_cubicos': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'step': '0.001',
                'placeholder': '0.00'
            }),
            'quantidade_volumes': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: 2 Contentores de 40ft ou 15 Paletes'
            }),
            'valor_cif': forms.TextInput(attrs={
                'class': 'moeda w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': '0,00',
                'inputmode': 'decimal'
            }),
            'data_validade': forms.DateInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'type': 'date'
            }, format='%Y-%m-%d'),
            'moeda_referencia': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'value': 'AOA'
            }),
            'cambio_referencia': forms.TextInput(attrs={
                'class': 'moeda w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': '0,00',
                'inputmode': 'decimal'
            }),
            'observacoes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all resize-none',
                'rows': '3',
                'placeholder': 'Observações adicionais...'
            }),
            'banco': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Nome do Banco'
            }),
            'numero_conta': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: 1234567890'
            }),
            'iban': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Ex: AO06001400000000000000100001'
            }),
            'instrucoes_envio': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all resize-none',
                'rows': '2',
                'placeholder': 'Ex: Por favor, enviar o comprovativo de transferência com a referência do número da Requisição'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                nif = Cliente.objects.filter(id=cliente_id).values_list('nif', flat=True).first()
                if nif:
                    self.fields['processo_aduaneiro'].queryset = DeclaracaoUnica.objects.filter(
                        nif_declarante=nif, status='Aprovada'
                    )
            except (ValueError, TypeError):
                pass


class RequisicaoFundoLinhaForm(forms.ModelForm):
    class Meta:
        model = RequisicaoFundoLinha
        fields = ['tipo_custo', 'descricao', 'documentada', 'despesa_tipo', 'valor', 'documento_justificativo']
        widgets = {
            'tipo_custo': forms.RadioSelect(attrs={
                'class': 'hidden'
            }),
            'descricao': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Descrição do custo'
            }),
            'documentada': forms.RadioSelect(attrs={
                'class': 'hidden'
            }),
            'despesa_tipo': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'id': 'id_despesa_tipo'
            }),
            'valor': forms.TextInput(attrs={
                'class': 'moeda w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': '0,00',
                'inputmode': 'decimal',
                'id': 'id_valor'
            }),
            'documento_justificativo': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 transition-all cursor-pointer'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Definir valores padrão se for criação nova
        if not self.instance.pk:
            # Padrão: Impostos e Documentada=Sim
            if not self.data:
                self.initial['tipo_custo'] = 'Impostos e Taxas Aduaneiras (AGT)'
                self.initial['documentada'] = True
        
        # Carregar opções de despesa_tipo baseado em documentada
        documentada = self.instance.documentada if self.instance.pk else self.initial.get('documentada', True)
        
        if documentada:
            self.fields['despesa_tipo'].choices = [('', 'Selecione uma despesa')] + RequisicaoFundoLinha.DESPESAS_DOCUMENTADAS
        else:
            self.fields['despesa_tipo'].choices = [('', 'Selecione uma despesa')] + RequisicaoFundoLinha.DESPESAS_NAODOCUMENTADAS
    
    def clean(self):
        cleaned_data = super().clean()
        documentada = cleaned_data.get('documentada')
        documento_justificativo = cleaned_data.get('documento_justificativo')
        despesa_tipo = cleaned_data.get('despesa_tipo')
        tipo_custo = cleaned_data.get('tipo_custo')
        valor = cleaned_data.get('valor')
        
        # Validar valor numérico se for string
        if valor and isinstance(valor, str):
            # Remover espaços e substituir vírgula por ponto
            valor_clean = valor.replace(' ', '').replace(',', '.')
            try:
                cleaned_data['valor'] = Decimal(valor_clean)
            except (ValueError, InvalidOperation):
                raise forms.ValidationError('Valor inválido. Use formato: 1000.00 ou 1.000,00')
        
        # Se documentada=True, o documento é obrigatório (mas só em criação ou se não tinha documento antes)
        if documentada and not documento_justificativo:
            # Verificar se já existe um documento na instância (edição)
            if not self.instance.pk or not self.instance.documento_justificativo:
                raise forms.ValidationError(
                    'Comprovativo da despesa é obrigatório quando a despesa é documentada.'
                )
        
        # despesa_tipo sempre obrigatório
        if not despesa_tipo:
            raise forms.ValidationError(
                'Tipo de despesa é obrigatório.'
            )
        
        return cleaned_data


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
            'honorarios_despachante': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'taxas_aduaneiras': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'emolumentos': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'despesas_operacionais': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'iva': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'outros_encargos': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'data_vencimento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
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
                        nif_declarante=nif, status='Aprovada'
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
            'valor_recebido': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
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
                    self.add_error('valor_recebido', f'O valor recebido excede o valor pendente desta factura ({fmt_kz(restante)} Kz).')

        return cleaned_data


class ReciboClienteUpdateForm(forms.ModelForm):
    class Meta:
        model = ReciboCliente
        fields = ['valor_recebido', 'forma_pagamento', 'data_pagamento', 'referencia_bancaria']
        widgets = {
            'valor_recebido': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
            'referencia_bancaria': forms.TextInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
        }


class NotaCreditoForm(forms.ModelForm):
    class Meta:
        model = NotaCredito
        fields = ['cliente', 'factura_relacionada', 'valor_creditado', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor_creditado': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'motivo': forms.Select(choices=[
                ('Erro de facturação', 'Erro de facturação'),
                ('Desconto posterior', 'Desconto posterior'),
                ('Devolução de valores', 'Devolução de valores'),
                ('Ajustes contabilísticos', 'Ajustes contabilísticos'),
            ], attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
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
                self.add_error('valor_creditado', f'O valor a creditar não pode exceder o valor total da factura ({fmt_kz(factura_relacionada.valor_total)} Kz).')

        return cleaned_data


class NotaDebitoForm(forms.ModelForm):
    class Meta:
        model = NotaDebito
        fields = ['cliente', 'factura_relacionada', 'valor', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'motivo': forms.Select(choices=[
                ('Taxas adicionais', 'Taxas adicionais'),
                ('Correções de valores', 'Correções de valores'),
                ('Encargos não considerados inicialmente', 'Encargos não considerados inicialmente'),
            ], attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
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
                self.add_error('valor', f'O valor a debitar não pode exceder o valor total da factura ({fmt_kz(factura_relacionada.valor_total)} Kz).')

        return cleaned_data


class FacturaReciboForm(forms.ModelForm):
    class Meta:
        model = FacturaRecibo
        fields = ['cliente', 'factura', 'valor', 'forma_pagamento', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
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
                self.add_error('valor', f'O valor excede o valor pendente desta factura ({fmt_kz(restante)} Kz).')

        return cleaned_data
