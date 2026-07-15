from django import forms
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from clientes.models import Cliente
from rh.models import Banca, FilialBanca
from aduaneiro.models import DeclaracaoUnica
from utils.format_kz import fmt_kz, parse_kz
from .models import (
    FacturaCliente, ReciboCliente,
    NotaCredito, NotaDebito, FacturaRecibo,
    RequisicaoFundo, RequisicaoFundoLinha
)


class ClienteNIFChoiceField(forms.ModelChoiceField):
    """Campo que mostra apenas o NIF do cliente no select."""
    def label_from_instance(self, obj):
        return obj.nif or str(obj.pk)


class RequisicaoFundoForm(forms.ModelForm):
    processo_aduaneiro = forms.ModelChoiceField(
        queryset=DeclaracaoUnica.objects.filter(status='Submetida'),
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
        })
    )

    class Meta:
        model = RequisicaoFundo
        fields = ['banca', 'filial', 'cliente', 'pessoa_contacto', 'processo_aduaneiro', 
                 'numero_bl_awb', 'meio_transporte', 'origem', 'destino', 'mercadoria_descricao',
                 'peso_bruto_kg', 'peso_liquido_kg', 'cbm_metros_cubicos', 'quantidade_volumes', 'valor_cif',
                 'taxa_iva', 'data_validade', 'moeda_referencia', 'cambio_referencia', 'observacoes']
        field_classes = {
            'cliente': ClienteNIFChoiceField,
        }
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
            'taxa_iva': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
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
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        banca_id = request.session.get('banca_id') if request else None
        
        # Scope processo_aduaneiro to user's banca DUs
        du_qs = DeclaracaoUnica.objects.filter(status='Submetida')
        if banca_id:
            du_qs = du_qs.filter(banca_id=banca_id)
        self.fields['processo_aduaneiro'].queryset = du_qs.order_by('-created_at')
        
        # On POST, refine by client if provided
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                nif = Cliente.objects.filter(id=cliente_id, banca_id=banca_id).values_list('nif', flat=True).first()
                if nif:
                    self.fields['processo_aduaneiro'].queryset = DeclaracaoUnica.objects.filter(
                        nif_declarante=nif, status='Submetida', banca_id=banca_id
                    ).order_by('-created_at')
            except (ValueError, TypeError):
                pass
        
        # Populate banca field scoped to user
        if banca_id:
            self.fields['banca'].queryset = Banca.objects.filter(id=banca_id)
            self.fields['filial'].queryset = FilialBanca.objects.filter(banca_id=banca_id)
        else:
            self.fields['banca'].queryset = Banca.objects.none()
            self.fields['filial'].queryset = FilialBanca.objects.none()
        
        # On POST, ensure processo_aduaneiro queryset includes the submitted value
        if self.is_bound and self.data.get('processo_aduaneiro'):
            submitted_du = DeclaracaoUnica.objects.filter(
                pk=self.data.get('processo_aduaneiro'), status='Submetida'
            )
            if banca_id:
                submitted_du = submitted_du.filter(banca_id=banca_id)
            if submitted_du.exists():
                self.fields['processo_aduaneiro'].queryset = submitted_du

    def clean(self):
        cleaned_data = super().clean()
        
        # Validate processo_aduaneiro: ensure it belongs to the same banca
        processo_id = cleaned_data.get('processo_aduaneiro')
        if processo_id:
            try:
                du = DeclaracaoUnica.objects.get(pk=processo_id.pk if hasattr(processo_id, 'pk') else processo_id)
                if du.status not in ('Submetida', 'Aprovada'):
                    raise forms.ValidationError(
                        'O processo aduaneiro selecionado deve ter status "Submetida" ou "Aprovada".'
                    )
            except DeclaracaoUnica.DoesNotExist:
                raise forms.ValidationError(
                    'O processo aduaneiro selecionado não existe.'
                )
        
        # Validate cliente belongs to same banca
        cliente = cleaned_data.get('cliente')
        banca = cleaned_data.get('banca')
        if cliente and banca and cliente.banca_id != banca.pk:
            raise forms.ValidationError(
                'O cliente seleccionado não pertence à banca selecionada.'
            )
        
        # Validate filial belongs to same banca
        filial = cleaned_data.get('filial')
        if filial and banca and filial.banca_id != banca.pk:
            raise forms.ValidationError(
                'A filial selecionada não pertence à banca selecionada.'
            )
        
        return cleaned_data


class RequisicaoFundoLinhaForm(forms.ModelForm):
    class Meta:
        model = RequisicaoFundoLinha
        fields = ['tipo_custo', 'descricao', 'documentada', 'despesa_tipo', 'valor', 'documento_justificativo']
        widgets = {
            'descricao': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': 'Descrição do custo'
            }),
            'documentada': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'despesa_tipo': forms.Select(attrs={
                'class': 'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
            }),
            'valor': forms.TextInput(attrs={
                'class': 'moeda w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl text-sm focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all',
                'placeholder': '0,00',
                'inputmode': 'decimal'
            }),
            'documento_justificativo': forms.FileInput(attrs={
                'class': 'w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 transition-all cursor-pointer'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if not self.instance.pk and not self.data:
            self.initial['documentada'] = True
        
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
        valor = cleaned_data.get('valor')
        
        if valor and isinstance(valor, str):
            valor_clean = valor.replace(' ', '').replace(',', '.')
            try:
                cleaned_data['valor'] = Decimal(valor_clean)
            except (ValueError, InvalidOperation):
                raise forms.ValidationError('Valor inválido. Use formato: 1000.00 ou 1.000,00')
        
        if documentada and not documento_justificativo:
            if not self.instance.pk or not self.instance.documento_justificativo:
                raise forms.ValidationError(
                    'Este campo é obrigatório para despesas documentadas. Anexe o comprovativo (PDF, imagem, etc.).'
                )
        
        if not despesa_tipo:
            raise forms.ValidationError(
                'Tipo de despesa é obrigatório.'
            )
        
        # Honorários do Despachante: mínimo 45.000 KZ
        valor = cleaned_data.get('valor', Decimal('0'))
        if cleaned_data.get('tipo_custo') == 'Honorários do Despachante' and valor < Decimal('45000'):
            cleaned_data['valor'] = Decimal('45000')
            self._valor_auto_corrigido = True
        
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
            'processo_aduaneiro': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
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
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        # Desabilitar cliente e processo em edição (não devem ser alterados)
        if self.instance and self.instance.pk:
            for campo in ('cliente', 'processo_aduaneiro', 'descricao'):
                self.fields[campo].disabled = True
                attrs = self.fields[campo].widget.attrs
                classes = attrs.get('class', '')
                if 'bg-gray-100' not in classes:
                    attrs['class'] = classes + ' bg-gray-100 dark:bg-gray-600 cursor-not-allowed'
        else:
            if banca_id:
                self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
            else:
                self.fields['cliente'].queryset = Cliente.objects.none()
            # Filtrar processos por cliente tanto em GET como POST
            cliente = None
            if self.is_bound and self.data.get('cliente'):
                try:
                    cliente = Cliente.objects.get(pk=int(self.data.get('cliente')), banca_id=banca_id) if banca_id else Cliente.objects.get(pk=int(self.data.get('cliente')))
                except (Cliente.DoesNotExist, ValueError, TypeError):
                    pass
            if cliente:
                nif = (cliente.nif or '').strip()
                if nif:
                    du_qs = DeclaracaoUnica.objects.filter(nif_declarante=nif)
                    if banca_id:
                        du_qs = du_qs.filter(banca_id=banca_id)
                    self.fields['processo_aduaneiro'].queryset = du_qs.order_by('-data_submissao')

    def clean_data_vencimento(self):
        data = self.cleaned_data.get('data_vencimento')
        if data and not self.instance.pk and data < timezone.now().date():
            raise forms.ValidationError('A data de vencimento não pode estar no passado.')
        return data

    def _clean_monetario(self, field_name):
        raw = self.cleaned_data.get(field_name)
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')

    def clean_honorarios_despachante(self):
        return self._clean_monetario('honorarios_despachante')

    def clean_taxas_aduaneiras(self):
        return self._clean_monetario('taxas_aduaneiras')

    def clean_emolumentos(self):
        return self._clean_monetario('emolumentos')

    def clean_despesas_operacionais(self):
        return self._clean_monetario('despesas_operacionais')

    def clean_iva(self):
        return self._clean_monetario('iva')

    def clean_outros_encargos(self):
        return self._clean_monetario('outros_encargos')

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
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        if banca_id:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
        else:
            self.fields['cliente'].queryset = Cliente.objects.none()
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                qs_factura = FacturaCliente.objects.filter(cliente_id=cliente_id)
                if banca_id:
                    qs_factura = qs_factura.filter(banca_id=banca_id)
                self.fields['factura'].queryset = qs_factura
            except (ValueError, TypeError):
                pass
        elif not self.is_bound:
            self.fields['factura'].queryset = FacturaCliente.objects.none()
        if self.instance and self.instance.pk and self.instance.valor_recebido:
            self.initial['valor_recebido'] = fmt_kz(self.instance.valor_recebido)

    def clean_valor_recebido(self):
        raw = self.cleaned_data.get('valor_recebido')
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.valor_recebido:
            self.initial['valor_recebido'] = fmt_kz(self.instance.valor_recebido)

    def clean_valor_recebido(self):
        raw = self.cleaned_data.get('valor_recebido')
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')


class NotaCreditoForm(forms.ModelForm):
    motivo_outro = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={
            'id': 'id_motivo_outro_nc',
            'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm',
            'placeholder': 'Descreva o motivo...'
        })
    )

    class Meta:
        model = NotaCredito
        fields = ['cliente', 'factura_relacionada', 'valor_creditado', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'id': 'id_cliente_nc', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'id': 'id_factura_relacionada_nc', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'valor_creditado': forms.TextInput(attrs={'class': 'moeda moeda-inteiro w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'motivo': forms.Select(choices=[
                ('Erro de facturação', 'Erro de facturação'),
                ('Desconto posterior', 'Desconto posterior'),
                ('Devolução de valores', 'Devolução de valores'),
                ('Ajustes contabilísticos', 'Ajustes contabilísticos'),
                ('__outro__', 'Outro'),
            ], attrs={'id': 'id_motivo_nc', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        if banca_id:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
            self.fields['factura_relacionada'].queryset = FacturaCliente.objects.select_related('cliente').filter(banca_id=banca_id)
        else:
            self.fields['cliente'].queryset = Cliente.objects.none()
            self.fields['factura_relacionada'].queryset = FacturaCliente.objects.none()
        self.fields['factura_relacionada'].required = True
        self.fields['factura_relacionada'].label_from_instance = lambda obj: (
            f"Factura {obj.numero_factura} - {obj.cliente.nome} - {fmt_kz(obj.valor_total)} KZ"
        )
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                qs = self.fields['factura_relacionada'].queryset or FacturaCliente.objects.all()
                if banca_id:
                    qs = qs.filter(banca_id=banca_id)
                self.fields['factura_relacionada'].queryset = qs.filter(cliente_id=cliente_id)
            except (ValueError, TypeError):
                pass
        if self.instance and self.instance.pk and self.instance.valor_creditado:
            self.initial['valor_creditado'] = fmt_kz(self.instance.valor_creditado)
        if self.instance and self.instance.pk and self.instance.motivo:
            if self.instance.motivo not in dict(self.base_fields['motivo'].widget.choices).values():
                self.initial['motivo'] = '__outro__'
                self.initial['motivo_outro'] = self.instance.motivo

    def clean_valor_creditado(self):
        raw = self.cleaned_data.get('valor_creditado')
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')

    def clean(self):
        cleaned_data = super().clean()
        motivo = cleaned_data.get('motivo')
        if motivo == '__outro__':
            motivo_outro = (cleaned_data.get('motivo_outro') or '').strip()
            if not motivo_outro:
                self.add_error('motivo_outro', 'Indique o motivo personalizado.')
            else:
                cleaned_data['motivo'] = motivo_outro
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

    def save(self, commit=True):
        motivo = self.cleaned_data.get('motivo')
        if motivo == '__outro__':
            motivo_outro = (self.cleaned_data.get('motivo_outro') or '').strip()
            if motivo_outro:
                self.instance.motivo = motivo_outro
        return super().save(commit)


class NotaDebitoForm(forms.ModelForm):
    motivo_outro = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={
            'id': 'id_motivo_outro_nd',
            'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm',
            'placeholder': 'Descreva o motivo...'
        })
    )

    class Meta:
        model = NotaDebito
        fields = ['cliente', 'factura_relacionada', 'valor', 'motivo', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'id': 'id_cliente_nd', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'factura_relacionada': forms.Select(attrs={'id': 'id_factura_relacionada_nd', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'valor': forms.TextInput(attrs={'class': 'moeda moeda-inteiro w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'motivo': forms.Select(choices=[
                ('Taxas adicionais', 'Taxas adicionais'),
                ('Correções de valores', 'Correções de valores'),
                ('Encargos não considerados inicialmente', 'Encargos não considerados inicialmente'),
                ('__outro__', 'Outro'),
            ], attrs={'id': 'id_motivo_nd', 'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        if banca_id:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
            self.fields['factura_relacionada'].queryset = FacturaCliente.objects.select_related('cliente').filter(banca_id=banca_id)
        else:
            self.fields['cliente'].queryset = Cliente.objects.none()
            self.fields['factura_relacionada'].queryset = FacturaCliente.objects.none()
        self.fields['factura_relacionada'].required = True
        self.fields['factura_relacionada'].label_from_instance = lambda obj: (
            f"Factura {obj.numero_factura} - {obj.cliente.nome} - {fmt_kz(obj.valor_total)} KZ"
        )
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                qs = self.fields['factura_relacionada'].queryset or FacturaCliente.objects.all()
                if banca_id:
                    qs = qs.filter(banca_id=banca_id)
                self.fields['factura_relacionada'].queryset = qs.filter(cliente_id=cliente_id)
            except (ValueError, TypeError):
                pass
        if self.instance and self.instance.pk and self.instance.valor:
            self.initial['valor'] = fmt_kz(self.instance.valor)
        if self.instance and self.instance.pk and self.instance.motivo:
            if self.instance.motivo not in dict(self.base_fields['motivo'].widget.choices).values():
                self.initial['motivo'] = '__outro__'
                self.initial['motivo_outro'] = self.instance.motivo

    def clean_valor(self):
        raw = self.cleaned_data.get('valor')
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        factura_relacionada = cleaned_data.get('factura_relacionada')
        valor = cleaned_data.get('valor')
        motivo = cleaned_data.get('motivo')

        if motivo == '__outro__':
            motivo_outro = (cleaned_data.get('motivo_outro') or '').strip()
            if not motivo_outro:
                self.add_error('motivo_outro', 'Indique o motivo personalizado.')
            else:
                cleaned_data['motivo'] = motivo_outro

        if factura_relacionada and cliente and factura_relacionada.cliente != cliente:
            self.add_error('factura_relacionada', 'A factura selecionada não pertence ao cliente escolhido.')

        if valor:
            if valor <= 0:
                self.add_error('valor', 'O valor deve ser maior que zero.')
            elif factura_relacionada and valor > factura_relacionada.valor_total:
                self.add_error('valor', f'O valor a debitar não pode exceder o valor total da factura ({fmt_kz(factura_relacionada.valor_total)} Kz).')

        return cleaned_data

    def save(self, commit=True):
        motivo = self.cleaned_data.get('motivo')
        if motivo == '__outro__':
            motivo_outro = (self.cleaned_data.get('motivo_outro') or '').strip()
            if motivo_outro:
                self.instance.motivo = motivo_outro
        return super().save(commit)


class FacturaReciboForm(forms.ModelForm):
    class Meta:
        model = FacturaRecibo
        fields = ['cliente', 'factura', 'valor', 'forma_pagamento', 'data']
        widgets = {
            'cliente': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'factura': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'valor': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm'}),
            'data': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        if banca_id:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
        else:
            self.fields['cliente'].queryset = Cliente.objects.none()
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                qs_factura = FacturaCliente.objects.filter(cliente_id=cliente_id, estado__in=['Pendente', 'Parcialmente Paga'])
                if banca_id:
                    qs_factura = qs_factura.filter(banca_id=banca_id)
                self.fields['factura'].queryset = qs_factura
            except (ValueError, TypeError):
                pass
        elif not self.is_bound:
            self.fields['factura'].queryset = FacturaCliente.objects.none()
        if self.instance and self.instance.pk and self.instance.valor:
            self.initial['valor'] = fmt_kz(self.instance.valor)

    def clean_valor(self):
        raw = self.cleaned_data.get('valor')
        if raw is None:
            return raw
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                raw = parse_kz(raw)
        try:
            return Decimal(str(raw)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Introduza um valor numérico válido (ex: 10000 ou 10.000,00).')

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
