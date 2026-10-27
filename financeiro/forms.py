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
    RequisicaoFundo, RequisicaoFundoLinha, FaturaEletronica,
    ConfiguracaoAGT, SerieFaturaEletronica
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
                 'peso_bruto_kg', 'peso_liquido_kg', 'quantidade_volumes', 'valor_cif',
                 'taxa_iva', 'data_validade', 'observacoes']
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
                'placeholder': 'Nome da pessoa de contacto',
                'disabled': True
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
        
        if not banca_id and request:
            from rh.models import Colaborador as _Col
            tipo = request.session.get('tipo_usuario', '')
            if tipo == 'colaborador':
                cid = request.session.get('colaborador_id')
                col = _Col.objects.filter(pk=cid).first()
            else:
                uid = request.session.get('usuario_id')
                col = _Col.objects.filter(usuario_id=uid).first()
            if col and col.banca_id:
                banca_id = col.banca_id
                request.session['banca_id'] = banca_id
                if col.filial_id:
                    request.session['colaborador_filial_id'] = col.filial_id
        
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
            'cliente': forms.Select(attrs={'id': 'id_cliente_recibo', 'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'factura': forms.Select(attrs={'id': 'id_factura_recibo', 'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'valor_recebido': forms.TextInput(attrs={'class': 'moeda w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'inputmode': 'decimal', 'placeholder': '0,00'}),
            'forma_pagamento': forms.Select(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
            'data_pagamento': forms.DateInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm', 'type': 'date'}, format='%Y-%m-%d'),
            'referencia_bancaria': forms.TextInput(attrs={'class': 'w-full px-4 py-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        banca_id = kwargs.pop('banca_id', None)
        super().__init__(*args, **kwargs)
        self._banca_id = banca_id
        if banca_id:
            self.fields['cliente'].queryset = Cliente.objects.filter(ativo=True, banca_id=banca_id).order_by('nome')
        else:
            self.fields['cliente'].queryset = Cliente.objects.none()
        if self.is_bound and self.data.get('cliente'):
            try:
                cliente_id = int(self.data.get('cliente'))
                qs_factura = FacturaCliente.objects.filter(
                    cliente_id=cliente_id,
                    estado__in=['Pendente', 'Parcialmente Paga']
                )
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

        if factura and factura.estado == 'Paga':
            self.add_error('factura', 'Esta factura já foi totalmente paga.')

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


_FE_INPUT_CLASS = (
    'w-full px-4 py-2.5 bg-gray-50 dark:bg-gray-700/50 border '
    'border-gray-200 dark:border-gray-600 rounded-xl text-sm '
    'focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all'
)


class FaturaEletronicaForm(forms.ModelForm):
    """Formulário de emissão de documentos para a Faturação Eletrónica da AGT.

    O documento fiscal deve estar ligado a uma Factura Cliente ou a uma
    Requisição de Fundos já existente; o total é derivado dessa origem.
    """

    class Meta:
        model = FaturaEletronica
        fields = ['cliente', 'tipo_documento', 'requisicao_fundo',
                  'factura_cliente', 'documento_origem_ref', 'motivo_ref',
                  'callback_url', 'observacoes']
        widgets = {
            'cliente': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'tipo_documento': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'requisicao_fundo': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'factura_cliente': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'documento_origem_ref': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'motivo_ref': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS,
                'maxlength': '60',
                'placeholder': 'Ex: Devolução de serviços, correção de valor...',
            }),
            'callback_url': forms.URLInput(attrs={
                'class': _FE_INPUT_CLASS,
                'placeholder': 'https://meusistema.co.ao/api/facturacaoelectronica/callback',
            }),
            'observacoes': forms.Textarea(attrs={
                'class': _FE_INPUT_CLASS + ' resize-none',
                'rows': '3',
                'placeholder': 'Observações adicionais para o documento fiscal...',
            }),
        }

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        banca_id = None
        if request is not None:
            banca_id = request.session.get('banca_id')
            if not banca_id:
                from rh.models import Colaborador as _Col
                tipo = request.session.get('tipo_usuario', '')
                if tipo == 'colaborador':
                    col = _Col.objects.filter(pk=request.session.get('colaborador_id')).first()
                else:
                    col = _Col.objects.filter(usuario_id=request.session.get('usuario_id')).first()
                if col and col.banca_id:
                    banca_id = col.banca_id

        clientes_qs = Cliente.objects.filter(ativo=True)
        requisicoes_qs = RequisicaoFundo.objects.select_related('cliente')
        facturas_qs = FacturaCliente.objects.select_related('cliente')
        # Documentos já registados na AGT, candidatos a referência de NC/ND.
        refs_qs = (
            FaturaEletronica.objects
            .filter(document_no__gt='', estado__in=['Enviada AGT', 'Aprovada AGT'])
            .select_related('cliente')
        )
        if self.instance.pk:
            refs_qs = refs_qs.exclude(pk=self.instance.pk)
        if banca_id:
            clientes_qs = clientes_qs.filter(banca_id=banca_id)
            requisicoes_qs = requisicoes_qs.filter(banca_id=banca_id)
            facturas_qs = facturas_qs.filter(banca_id=banca_id)
            refs_qs = refs_qs.filter(banca_id=banca_id)
        elif request is not None:
            # Sem banca resolvida não se expõem dados de outras bancas.
            clientes_qs = clientes_qs.none()
            requisicoes_qs = requisicoes_qs.none()
            facturas_qs = facturas_qs.none()
            refs_qs = refs_qs.none()

        self.fields['cliente'].queryset = clientes_qs.order_by('nome')

        # Refina os documentos de origem pelo cliente escolhido.
        cliente_id = self.data.get('cliente') if self.is_bound else None
        if cliente_id:
            try:
                cliente_id = int(cliente_id)
                requisicoes_qs = requisicoes_qs.filter(cliente_id=cliente_id)
                facturas_qs = facturas_qs.filter(cliente_id=cliente_id)
                refs_qs = refs_qs.filter(cliente_id=cliente_id)
            except (TypeError, ValueError):
                pass

        self.fields['requisicao_fundo'].queryset = requisicoes_qs.order_by('-data_emissao')
        self.fields['factura_cliente'].queryset = facturas_qs.order_by('-data_emissao')
        self.fields['documento_origem_ref'].queryset = refs_qs.order_by('-data_emissao')
        self.fields['documento_origem_ref'].required = False
        self.fields['motivo_ref'].required = False

        self.fields['requisicao_fundo'].label_from_instance = lambda obj: (
            f"{obj.numero_requisicao} - {obj.cliente.nome} - {fmt_kz(obj.total_geral)} KZ"
        )
        self.fields['factura_cliente'].label_from_instance = lambda obj: (
            f"{obj.numero_factura} - {obj.cliente.nome} - {fmt_kz(obj.valor_total)} KZ"
        )
        self.fields['documento_origem_ref'].label_from_instance = lambda obj: (
            f"{obj.document_no} - {obj.cliente.nome} - {fmt_kz(obj.total_geral)} KZ"
        )

        # Sugere a URL pública de callback configurada para o sistema.
        if not self.is_bound and not self.instance.callback_url:
            from django.conf import settings as _settings
            self.fields['callback_url'].initial = getattr(_settings, 'AGT_CALLBACK_URL', '') or ''

    def clean_callback_url(self):
        url = (self.cleaned_data.get('callback_url') or '').strip()
        if url and not url.lower().startswith('https://'):
            raise forms.ValidationError('O Callback URL deve usar HTTPS (https://...).')
        return url

    def clean(self):
        cleaned_data = super().clean()
        cliente = cleaned_data.get('cliente')
        requisicao = cleaned_data.get('requisicao_fundo')
        factura = cleaned_data.get('factura_cliente')
        tipo = cleaned_data.get('tipo_documento')
        ref = cleaned_data.get('documento_origem_ref')

        # A referência ao documento original só é exigida (e aplicável) em NC/ND.
        if tipo in ('NOTA_CREDITO', 'NOTA_DEBITO'):
            if ref is None:
                self.add_error(
                    'documento_origem_ref',
                    'Escolha o documento fiscal de origem (factura já registada na AGT).',
                )
            elif not ref.document_no:
                self.add_error(
                    'documento_origem_ref',
                    'O documento de origem ainda não foi registado na AGT.',
                )
            elif cliente and ref.cliente_id != cliente.pk:
                self.add_error(
                    'documento_origem_ref',
                    'O documento de origem pertence a outro cliente.',
                )
        else:
            cleaned_data['documento_origem_ref'] = None
            cleaned_data['motivo_ref'] = ''

        if not requisicao and not factura:
            raise forms.ValidationError(
                'Selecione uma Factura Cliente ou uma Requisição de Fundos como origem do documento.'
            )

        if requisicao and cliente and requisicao.cliente_id != cliente.pk:
            self.add_error('requisicao_fundo', 'A requisição selecionada não pertence ao cliente escolhido.')

        if factura and cliente and factura.cliente_id != cliente.pk:
            self.add_error('factura_cliente', 'A factura selecionada não pertence ao cliente escolhido.')

        if requisicao and factura:
            self.add_error(
                'factura_cliente',
                'Escolha apenas uma origem: Factura Cliente ou Requisição de Fundos.',
            )

        # Evita emitir dois documentos eletrónicos ativos para a mesma origem.
        ativos = ['Rascunho', 'Em Fila', 'Enviada AGT', 'Aprovada AGT']
        duplicados = FaturaEletronica.objects.filter(estado__in=ativos)
        if self.instance.pk:
            duplicados = duplicados.exclude(pk=self.instance.pk)
        if factura and duplicados.filter(factura_cliente=factura).exists():
            self.add_error('factura_cliente', 'Já existe uma fatura eletrónica ativa para esta factura.')
        if requisicao and duplicados.filter(requisicao_fundo=requisicao).exists():
            self.add_error('requisicao_fundo', 'Já existe uma fatura eletrónica ativa para esta requisição.')

        return cleaned_data


_FE_KEY_INPUT_CLASS = _FE_INPUT_CLASS + ' font-mono text-xs resize-none'


def _validar_pem_privada(valor, rotulo):
    """Valida que o valor é um PEM de chave privada (RSA) válido. Vazio é aceite."""
    valor = (valor or '').strip()
    if not valor:
        return ''
    from cryptography.hazmat.primitives import serialization
    try:
        serialization.load_pem_private_key(valor.encode('utf-8'), password=None)
    except Exception:
        raise forms.ValidationError(f'A {rotulo} não é um PEM de chave privada válido.')
    return valor


class ConfiguracaoAGTForm(forms.ModelForm):
    """Configuração da integração com a Faturação Eletrónica da AGT.

    A banca é resolvida a partir da sessão (não é escolhida no formulário).
    As chaves privadas PEM são guardadas cifradas pelo modelo.
    """

    class Meta:
        model = ConfiguracaoAGT
        fields = [
            'ativo', 'ambiente', 'tax_registration_number',
            'product_id', 'product_version', 'software_validation_number',
            'signature_version', 'estabelecimento', 'eac_code',
            'software_private_key', 'emissor_private_key', 'agt_public_key',
            'submit_url', 'query_url', 'serie_url', 'callback_url',
        ]
        widgets = {
            'ativo': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary',
            }),
            'ambiente': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'tax_registration_number': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: 5000123456',
            }),
            'product_id': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: SICDOA',
            }),
            'product_version': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: 1.0.0',
            }),
            'software_validation_number': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Nº de certificação atribuído pela AGT',
            }),
            'signature_version': forms.NumberInput(attrs={
                'class': _FE_INPUT_CLASS, 'min': '1',
            }),
            'estabelecimento': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: SEDE',
            }),
            'eac_code': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: 47110',
            }),
            'software_private_key': forms.Textarea(attrs={
                'class': _FE_KEY_INPUT_CLASS, 'rows': '5', 'autocomplete': 'off',
                'placeholder': '-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----',
            }),
            'emissor_private_key': forms.Textarea(attrs={
                'class': _FE_KEY_INPUT_CLASS, 'rows': '5', 'autocomplete': 'off',
                'placeholder': '-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----',
            }),
            'agt_public_key': forms.Textarea(attrs={
                'class': _FE_KEY_INPUT_CLASS, 'rows': '4', 'autocomplete': 'off',
                'placeholder': '-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----',
            }),
            'submit_url': forms.URLInput(attrs={'class': _FE_INPUT_CLASS}),
            'query_url': forms.URLInput(attrs={'class': _FE_INPUT_CLASS}),
            'serie_url': forms.URLInput(attrs={'class': _FE_INPUT_CLASS}),
            'callback_url': forms.URLInput(attrs={
                'class': _FE_INPUT_CLASS,
                'placeholder': 'https://meusistema.co.ao/api/facturacaoelectronica/callback',
            }),
        }
        labels = {
            'tax_registration_number': 'NIF do Contribuinte',
            'software_validation_number': 'Nº de Certificação do Software',
            'software_private_key': 'Chave Privada do Software (PEM)',
            'emissor_private_key': 'Chave Privada do Emissor (PEM)',
            'agt_public_key': 'Chave Pública da AGT (PEM)',
            'submit_url': 'URL registarFactura (opcional)',
            'query_url': 'URL obterEstado (opcional)',
            'serie_url': 'URL solicitarSerie (opcional)',
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk and not self.instance.callback_url:
            from django.conf import settings as _settings
            self.fields['callback_url'].initial = getattr(_settings, 'AGT_CALLBACK_URL', '') or ''

    def clean_software_private_key(self):
        return _validar_pem_privada(self.cleaned_data.get('software_private_key'), 'chave privada do software')

    def clean_emissor_private_key(self):
        return _validar_pem_privada(self.cleaned_data.get('emissor_private_key'), 'chave privada do emissor')

    def clean_agt_public_key(self):
        valor = (self.cleaned_data.get('agt_public_key') or '').strip()
        if not valor:
            return ''
        from cryptography.hazmat.primitives import serialization
        try:
            serialization.load_pem_public_key(valor.encode('utf-8'))
        except Exception:
            raise forms.ValidationError('A chave pública da AGT não é um PEM válido.')
        return valor

    def clean_callback_url(self):
        url = (self.cleaned_data.get('callback_url') or '').strip()
        if url and not url.lower().startswith('https://'):
            raise forms.ValidationError('O Callback URL deve usar HTTPS (https://...).')
        return url

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('ativo'):
            if not (cleaned_data.get('tax_registration_number') or '').strip():
                self.add_error('tax_registration_number', 'Indique o NIF do contribuinte para ativar a integração.')
            if not (cleaned_data.get('software_validation_number') or '').strip():
                self.add_error('software_validation_number', 'Indique o nº de certificação do software.')
        return cleaned_data


class SerieFaturaEletronicaForm(forms.ModelForm):
    """Criação/edição de uma série de numeração da Faturação Eletrónica.

    O código fiscal e os limites de numeração são atribuídos pela AGT na
    comunicação (serviço solicitarSerie), por isso não são editáveis aqui.
    """

    class Meta:
        model = SerieFaturaEletronica
        fields = ['tipo_documento', 'ano', 'referencia', 'estabelecimento',
                  'contingencia', 'numero_inicial']
        widgets = {
            'tipo_documento': forms.Select(attrs={'class': _FE_INPUT_CLASS}),
            'ano': forms.NumberInput(attrs={'class': _FE_INPUT_CLASS, 'min': '2000', 'max': '2100'}),
            'referencia': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: NORMAL',
            }),
            'estabelecimento': forms.TextInput(attrs={
                'class': _FE_INPUT_CLASS, 'placeholder': 'Ex: SEDE',
            }),
            'contingencia': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary',
            }),
            'numero_inicial': forms.NumberInput(attrs={'class': _FE_INPUT_CLASS, 'min': '1'}),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.instance.pk:
            self.fields['ano'].initial = timezone.now().year

    def clean_ano(self):
        ano = self.cleaned_data.get('ano')
        if ano and not (2000 <= ano <= 2100):
            raise forms.ValidationError('Indique um ano civil válido (2000–2100).')
        return ano

    def clean_numero_inicial(self):
        numero = self.cleaned_data.get('numero_inicial')
        if numero is not None and int(numero) < 1:
            raise forms.ValidationError('O número inicial deve ser no mínimo 1.')
        return numero

    def clean_referencia(self):
        referencia = (self.cleaned_data.get('referencia') or '').strip().upper()
        if not referencia:
            raise forms.ValidationError('Indique uma referência interna para a série.')
        return referencia
