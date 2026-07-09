from datetime import date as date_type
from decimal import Decimal
import json

from django.db import models, transaction
from django.db.models import F, Sum
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica


class RequisicaoFundo(models.Model):
    """Modelo para Requisição de Fundos - Fatura Proforma"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aceite', 'Aceite'),
        ('Rejeitada', 'Rejeitada'),
        ('Anulada', 'Anulada'),
    ]
    
    # Cabeçalho - Documento
    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='requisicoes_fundos',
                               null=True, blank=True, verbose_name='Banca')
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='requisicoes_fundos',
                                verbose_name='Filial')
    numero_requisicao = models.CharField(max_length=50, unique=True, blank=True,
                                        verbose_name='Número da Requisição', db_index=True)
    data_emissao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Emissão', db_index=True)
    data_validade = models.DateField(verbose_name='Data de Validade', db_index=True)
    moeda_referencia = models.CharField(max_length=3, default='AOA', verbose_name='Moeda')
    cambio_referencia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                            verbose_name='Câmbio de Referência')
    
    # Dados do Cliente
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='requisicoes_fundos',
                                verbose_name='Cliente')
    pessoa_contacto = models.CharField(max_length=200, blank=True, verbose_name='Pessoa de Contacto')
    
    # Referências do Processo Aduaneiro
    processo_aduaneiro = models.ForeignKey(DeclaracaoUnica, on_delete=models.CASCADE,
                                          related_name='requisicoes_fundos',
                                          verbose_name='Processo Aduaneiro')
    
    # Status
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente',
                             db_index=True, verbose_name='Estado')
    
    # Totalizações
    subtotal_geral = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                        verbose_name='Subtotal Geral')
    iva_honorarios = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                        verbose_name='IVA (Honorários)')
    retencao = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                   verbose_name='Retenção')
    total_geral = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                     verbose_name='Total Geral a Pagar')
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                    verbose_name='Valor Pago')
    
    # Metadados
    criado_por_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador', db_index=True)
    criado_por_nome = models.CharField(max_length=200, blank=True, default='',
                                      verbose_name='Nome do Criador')
    observacoes = models.TextField(blank=True, default='', verbose_name='Observações')
    
    # Seção 3 - Referências do Processo Aduaneiro (Carga) - Extraídos do DeclaracaoUnica
    numero_bl_awb = models.CharField(max_length=100, blank=True, verbose_name='Número B/L/AWB/Carta Porte')
    meio_transporte = models.CharField(max_length=100, blank=True, verbose_name='Meio de Transporte/Navio/Voo')
    origem = models.CharField(max_length=100, blank=True, verbose_name='Origem (País/Porto/Aeroporto)')
    destino = models.CharField(max_length=100, blank=True, verbose_name='Destino (País/Porto/Aeroporto)')
    mercadoria_descricao = models.TextField(blank=True, verbose_name='Descrição Sumária da Mercadoria')
    peso_bruto_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Peso Bruto (Kg)')
    peso_liquido_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Peso Líquido (Kg)')
    cbm_metros_cubicos = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name='CBM (Metros cúbicos)')
    quantidade_volumes = models.CharField(max_length=100, blank=True, verbose_name='Quantidade e Tipo de Volumes')
    valor_cif = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name='Valor CIF')
    
    instrucoes_envio = models.TextField(blank=True, verbose_name='Instruções de Envio')
    
    # Seção 7 - Validação e Fecho
    assinatura_digital = models.TextField(blank=True, verbose_name='Assinatura Digital (Base64)')
    codigo_qr = models.ImageField(upload_to='requisicoes_fundos/qr/%Y/%m/%d/', null=True, blank=True, verbose_name='Código QR')
    
    class Meta:
        db_table = 'financeiro_requisicao_fundo'
        verbose_name = 'Requisição de Fundos'
        verbose_name_plural = 'Requisições de Fundos'
        ordering = ['-data_emissao']
        indexes = [
            models.Index(fields=['estado', '-data_emissao'], name='ix_rf_estado_data'),
            models.Index(fields=['cliente', 'estado'], name='ix_rf_cliente_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_rf_banca_filial'),
        ]

    def _gerar_numero_requisicao(self):
        """Gera número sequencial: RF-2026/001"""
        ano = timezone.now().year
        ultimo = (
            RequisicaoFundo.objects
            .filter(numero_requisicao__startswith=f'RF-{ano}/')
            .order_by('-numero_requisicao')
            .first()
        )
        if ultimo and ultimo.numero_requisicao:
            try:
                seq = int(ultimo.numero_requisicao.split('/')[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        return f'RF-{ano}/{seq:03d}'

    def save(self, *args, **kwargs):
        if not self.numero_requisicao:
            self.numero_requisicao = self._gerar_numero_requisicao()
        
        # Salvar primeiro para ter ID (necessário para acessar relacionamentos)
        super().save(*args, **kwargs)
        
        # Recalcular totais APÓS salvar (agora tem ID)
        self._recalcular_totais()
        
        # Gerar assinatura digital e QR code
        self._gerar_assinatura_digital()
        self._gerar_codigo_qr()
        
        # Salvar novamente com totais recalculados
        super().save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral', 
                                    'assinatura_digital'])

    def _recalcular_totais(self):
        """Recalcula todos os totais baseado nos items"""
        linhas = self.linhas.all()
        
        # Subtotal = soma de todos os items
        self.subtotal_geral = sum(
            (linha.valor or 0) for linha in linhas
        )
        
        # IVA = 14% sobre o Subtotal (todas as linhas)
        self.iva_honorarios = (self.subtotal_geral * Decimal('0.14')).quantize(Decimal('0.01'))
        
        # Retenção = 6.5% sobre Honorários do Despachante (iteração em memória)
        valor_honorarios = sum(
            (linha.valor or 0) for linha in linhas
            if linha.tipo_custo == 'Honorários do Despachante'
        )
        
        self.retencao = (valor_honorarios * Decimal('0.065')).quantize(Decimal('0.01'))
        
        # Total = Subtotal + IVA + Retenção
        self.total_geral = (self.subtotal_geral + self.iva_honorarios + self.retencao).quantize(Decimal('0.01'))

    def _gerar_assinatura_digital(self):
        """Gera assinatura digital SHA-256 Base64 da requisição"""
        import hashlib
        import json
        import base64
        
        dados_assinatura = {
            'numero_requisicao': self.numero_requisicao,
            'cliente_nif': self.cliente.nif,
            'total_geral': str(self.total_geral),
            'data_emissao': str(self.data_emissao),
            'banca_nif': self.banca.nif if self.banca else '',
        }
        
        dados_json = json.dumps(dados_assinatura, sort_keys=True, ensure_ascii=False)
        hash_bytes = hashlib.sha256(dados_json.encode('utf-8')).digest()
        self.assinatura_digital = base64.b64encode(hash_bytes).decode('utf-8')

    def _gerar_codigo_qr(self):
        """Gera código QR com informações da requisição"""
        try:
            import qrcode
            from django.core.files.base import ContentFile
            from io import BytesIO
            
            # Dados do QR code
            dados_qr = f"RF:{self.numero_requisicao}|NIF:{self.cliente.nif}|TOTAL:{self.total_geral}|DATA:{self.data_emissao.strftime('%Y-%m-%d')}"
            
            # Gerar QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(dados_qr)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Salvar em buffer
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            # Salvar no modelo
            filename = f'requisicoes_fundos/qr/{self.numero_requisicao}.png'
            self.codigo_qr.save(filename, ContentFile(buffer.getvalue()), save=False)
        except ImportError:
            # Se qrcode não está instalado, continua sem QR
            pass

    def __str__(self):
        return f"RF {self.numero_requisicao} - {self.cliente.nome}"
    
    @property
    def saldo_pendente(self):
        """Calcula o saldo pendente (Total - Valor Pago)"""
        return (self.total_geral - self.valor_pago).quantize(Decimal('0.01'))
    
    @property
    def valor_total_extenso(self):
        """Converte o valor total para extenso em Kwanzas"""
        def numero_para_extenso(num):
            if num == 0:
                return 'zero'

            unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
            dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
            teens = ['dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove']
            centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']

            def ate_999(n):
                """Converte número de 0 a 999 para extenso. Retorna '' para 0."""
                if n == 0:
                    return ''
                elif n < 10:
                    return unidades[n]
                elif n < 20:
                    return teens[n - 10]
                elif n < 100:
                    d, u = divmod(n, 10)
                    if u == 0:
                        return dezenas[d]
                    return f"{dezenas[d]} e {unidades[u]}"
                else:
                    c, resto = divmod(n, 100)
                    if c == 1 and resto == 0:
                        return 'cem'
                    elif resto == 0:
                        return centenas[c]
                    return f"{centenas[c]} e {ate_999(resto)}"

            # Bilhões (até 999 bilhões)
            if num >= 1_000_000_000:
                bilhoes, resto = divmod(num, 1_000_000_000)
                b_txt = 'um bilhão' if bilhoes == 1 else f"{ate_999(bilhoes)} bilhões"
                if resto == 0:
                    return b_txt
                return f"{b_txt} e {numero_para_extenso(resto)}"

            # Milhões
            if num >= 1_000_000:
                milhoes, resto = divmod(num, 1_000_000)
                m_txt = 'um milhão' if milhoes == 1 else f"{ate_999(milhoes)} milhões"
                if resto == 0:
                    return m_txt
                elif resto < 1000:
                    return f"{m_txt} e {ate_999(resto)}"
                else:
                    return f"{m_txt} e {numero_para_extenso(resto)}"

            # Milhares
            if num >= 1000:
                milhares, resto = divmod(num, 1000)
                m_txt = 'mil' if milhares == 1 else f"{ate_999(milhares)} mil"
                if resto == 0:
                    return m_txt
                # Usar "e" quando o resto é < 100 ou é múltiplo de 100, senão vírgula
                conector = ' e ' if resto < 100 or resto % 100 == 0 else ' e '
                return f"{m_txt}{conector}{ate_999(resto)}"

            return ate_999(num)

        try:
            total = int(self.total_geral)
            if total < 0:
                return f"menos {numero_para_extenso(-total).capitalize()} kwanzas"
            extenso = numero_para_extenso(total)
            # Incluir os cêntimos se existirem
            centavos = round((self.total_geral - int(self.total_geral)) * 100)
            if centavos > 0:
                centavos_txt = numero_para_extenso(int(centavos))
                return f"{extenso.capitalize()} kwanzas e {centavos_txt} cêntimos"
            return f"{extenso.capitalize()} kwanzas"
        except Exception:
            return f"{self.total_geral} kwanzas"


class RequisicaoFundoLinha(models.Model):
    """Linhas de custos da Requisição de Fundos"""
    
    TIPOS_CUSTO = [
        ('Impostos e Taxas Aduaneiras (AGT)', 'Impostos e Taxas Aduaneiras (AGT)'),
        ('Despesas Portuárias e Terminais', 'Despesas Portuárias e Terminais'),
        ('Logística e Transporte', 'Logística e Transporte'),
        ('Honorários do Despachante', 'Honorários do Despachante'),
        ('Outras Despesas', 'Outras Despesas'),
    ]
    
    DESPESAS_DOCUMENTADAS = [
        ('Direitos e importações', 'Direitos e importações'),
        ('Emolumentos Gerais AD', 'Emolumentos Gerais AD'),
        ('IEC na Importação', 'IEC na Importação'),
        ('IVA na Importação', 'IVA na Importação'),
        ('Multas', 'Multas'),
        ('Emissão DAR', 'Emissão DAR'),
        ('Validação Carta porte', 'Validação Carta porte'),
        ('Validação B/L', 'Validação B/L'),
        ('Emissão/Correção – AWB', 'Emissão/Correção – AWB'),
        ('Emissão Pertence', 'Emissão Pertence'),
        ('ENANA', 'ENANA'),
        ('EP 13', 'EP 13'),
        ('EP 14', 'EP 14'),
        ('EP 15', 'EP 15'),
        ('Adicional EP 17', 'Adicional EP 17'),
        ('Emissão de Certificados', 'Emissão de Certificados'),
        ('Transport', 'Transport'),
        ('Transporte Inter-provincial', 'Transporte Inter-provincial'),
        ('Caução do Contentor', 'Caução do Contentor'),
        ('Sobrestadia de Serviço', 'Sobrestadia de Serviço'),
        ('Pagamento do PIP', 'Pagamento do PIP'),
        ('EP 17 – FAYOL', 'EP 17 – FAYOL'),
        ('Validação do Delivery', 'Validação do Delivery'),
        ('Taxa Administrativa', 'Taxa Administrativa'),
        ('Inspeção Sanitária', 'Inspeção Sanitária'),
        ('JUP', 'JUP'),
        ('Factura de Exportação', 'Factura de Exportação'),
        ('Multas e Desdobramento', 'Multas e Desdobramento'),
        ('Outras despesas', 'Outras despesas'),
    ]
    
    DESPESAS_NAODOCUMENTADAS = [
        ('Honorários', 'Honorários'),
        ('Franquias', 'Franquias'),
        ('Inerentes', 'Inerentes'),
        ('DU Provisório', 'DU Provisório'),
        ('Prestação de Serviço', 'Prestação de Serviço'),
        ('Impressos e Selos', 'Impressos e Selos'),
        ('Fotocopias', 'Fotocopias'),
        ('Carga/Descarga', 'Carga/Descarga'),
        ('Licenciamento', 'Licenciamento'),
        ('Nossa Agencia', 'Nossa Agencia'),
        ('Viação e Transito', 'Viação e Transito'),
        ('Aluguer de Pronto Soc', 'Aluguer de Pronto Soc'),
        ('Agencia Exportação', 'Agencia Exportação'),
        ('Estiva', 'Estiva'),
        ('Risco', 'Risco'),
        ('Transporte', 'Transporte'),
        ('Outras despesas', 'Outras despesas'),
        ('Diversos', 'Diversos'),
    ]
    
    requisicao = models.ForeignKey(RequisicaoFundo, on_delete=models.CASCADE,
                                   related_name='linhas', verbose_name='Requisição')
    tipo_custo = models.CharField(max_length=50, choices=TIPOS_CUSTO,
                                 verbose_name='Tipo de Custo', db_index=True)
    descricao = models.CharField(max_length=255, verbose_name='Descrição')
    documentada = models.BooleanField(default=False, verbose_name='Documentada', db_index=True)
    despesa_tipo = models.CharField(max_length=50, blank=True, null=True,
                                   verbose_name='Tipo de Despesa')
    valor = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Valor')
    documento_justificativo = models.FileField(upload_to='requisicoes_fundos/%Y/%m/%d/',
                                               null=True, blank=True,
                                               verbose_name='Documento Justificativo')
    ordem = models.PositiveSmallIntegerField(default=0, verbose_name='Ordem', db_index=True)
    
    class Meta:
        db_table = 'financeiro_requisicao_linha'
        verbose_name = 'Linha de Requisição'
        verbose_name_plural = 'Linhas de Requisição'
        ordering = ['ordem']
        indexes = [
            models.Index(fields=['requisicao', 'tipo_custo'], name='ix_rfl_requisicao_tipo'),
        ]

    def save(self, *args, **kwargs):
        # Validar honorário mínimo
        if self.tipo_custo == 'Honorários do Despachante' and self.valor < 45000:
            self.valor = Decimal('45000.00')
        
        super().save(*args, **kwargs)
        # Recalcular totais da requisição
        self.requisicao._recalcular_totais()
        self.requisicao.save(update_fields=['subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral'])

    def __str__(self):
        return f"{self.requisicao.numero_requisicao} - {self.descricao}"


class FacturaCliente(models.Model):
    """Modelo para Facturas Finais de Clientes"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Parcialmente Paga', 'Parcialmente Paga'),
        ('Paga', 'Paga'),
        ('Cancelada', 'Cancelada'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='facturas_cliente',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='facturas_cliente')
    numero_factura = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Factura')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='facturas_cliente', verbose_name='Cliente')
    processo_aduaneiro = models.ForeignKey(DeclaracaoUnica, on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas_cliente', verbose_name='Processo Aduaneiro')
    
    # Detalhes dos custos
    honorarios_despachante = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Honorários do Despachante')
    taxas_aduaneiras = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Taxas Aduaneiras')
    emolumentos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Emolumentos')
    despesas_operacionais = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Despesas Operacionais')
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='IVA')
    outros_encargos = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Outros Encargos')
    retencao = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Retenção')
    
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Total')
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name='Valor Pago')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True, verbose_name='Estado')
    data_emissao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Emissão', db_index=True)
    data_vencimento = models.DateField(verbose_name='Data de Vencimento', db_index=True)
    descricao = models.TextField(verbose_name='Descrição')
    
    criado_por_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador', db_index=True)
    criado_por_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')

    requisicao_fundo = models.ForeignKey(
        'RequisicaoFundo', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='facturas', verbose_name='Requisição de Fundos'
    )

    class Meta:
        db_table = 'financeiro_factura_cliente'
        verbose_name = 'Factura de Cliente'
        verbose_name_plural = 'Facturas de Clientes'
        ordering = ['-data_emissao']
        indexes = [
            models.Index(fields=['estado', '-data_emissao'], name='ix_factura_estado_data'),
            models.Index(fields=['cliente', 'estado'], name='ix_factura_cliente_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_factura_banca_filial'),
        ]

    def clean(self):
        if not self.pk and self.data_vencimento and self.data_vencimento < timezone.now().date():
            raise ValidationError({'data_vencimento': 'A data de vencimento não pode estar no passado.'})

    def _gerar_numero_factura(self):
        """Gera número sequencial: FT-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            FacturaCliente.objects
            .filter(numero_factura__startswith=f'FT-{ano}-')
            .order_by('-numero_factura')
            .first()
        )
        if ultimo and ultimo.numero_factura:
            try:
                seq = int(ultimo.numero_factura.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'FT-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_valor = Decimal('0')
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = FacturaCliente.objects.get(pk=self.pk)
            old_valor = old_self.valor_total
            old_estado = old_self.estado

        if not kwargs.pop('skip_recalculo', False):
            self.valor_total = (
                self.honorarios_despachante + 
                self.taxas_aduaneiras + 
                self.emolumentos + 
                self.despesas_operacionais + 
                self.iva + 
                self.outros_encargos +
                self.retencao
            )

        if not self.numero_factura:
            self.numero_factura = self._gerar_numero_factura()

        super().save(*args, **kwargs)

        with transaction.atomic():
            cliente = Cliente.objects.select_for_update().get(pk=self.cliente.pk)
            novo_valor = Decimal('0') if self.estado == 'Cancelada' else self.valor_total
            antigo_debito = Decimal('0') if old_estado == 'Cancelada' else old_valor
            diff = novo_valor - antigo_debito
            if diff != 0:
                cliente.saldo_conta_corrente -= diff
                cliente.save(update_fields=['saldo_conta_corrente'])
            self.cliente.refresh_from_db()

        # Finalizar DU se a fatura foi paga e está vinculada a um processo aduaneiro
        if self.estado == 'Paga' and self.processo_aduaneiro_id:
            try:
                du = DeclaracaoUnica.objects.get(pk=self.processo_aduaneiro_id)
                if du.status != 'Finalizada':
                    du.status = 'Finalizada'
                    du.save(update_fields=['status'])
            except DeclaracaoUnica.DoesNotExist:
                pass

    def __str__(self):
        return f"Factura {self.numero_factura} - {self.cliente.nome} - {self.valor_total}"


class ReciboCliente(models.Model):
    """Modelo para Recibos de Pagamento de Clientes"""
    
    FORMAS_PAGAMENTO = [
        ('Transferência Bancária', 'Transferência Bancária'),
        ('Multicaixa', 'Multicaixa'),
        ('TPAs', 'TPAs'),
        ('Depósito Bancário', 'Depósito Bancário'),
        ('Numerário', 'Numerário'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='recibos_cliente',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='recibos_cliente')
    numero_recibo = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número do Recibo')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='recibos_cliente', verbose_name='Cliente')
    factura = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='recibos', verbose_name='Factura')
    requisicao_fundo = models.ForeignKey(RequisicaoFundo, on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name='recibos_pagamento', verbose_name='Requisição de Fundo')
    valor_recebido = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Recebido')
    forma_pagamento = models.CharField(max_length=50, choices=FORMAS_PAGAMENTO, verbose_name='Forma de Pagamento', db_index=True)
    data_pagamento = models.DateField(verbose_name='Data do Pagamento', db_index=True)
    referencia_bancaria = models.CharField(max_length=100, blank=True, default='', verbose_name='Referência Bancária')
    
    utilizador_responsavel_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Responsável')
    utilizador_responsavel_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Responsável')
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação', db_index=True)
    estado = models.CharField(max_length=20, choices=[('Pendente', 'Pendente'), ('Cancelado', 'Cancelado')], default='Pendente', null=True, blank=True, db_index=True, verbose_name='Estado')

    class Meta:
        db_table = 'financeiro_recibo_cliente'
        verbose_name = 'Recibo de Cliente'
        verbose_name_plural = 'Recibos de Clientes'
        ordering = ['-data_criacao']
        indexes = [
            models.Index(fields=['cliente', 'estado'], name='ix_recibo_cliente_estado'),
            models.Index(fields=['factura', 'estado'], name='ix_recibo_factura_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_recibo_banca_filial'),
        ]

    def clean(self):
        if self.data_pagamento and self.data_pagamento > timezone.now().date():
            raise ValidationError({'data_pagamento': 'A data de pagamento não pode estar no futuro.'})

    def _gerar_numero_recibo(self):
        """Gera número sequencial: REC-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            ReciboCliente.objects
            .filter(numero_recibo__startswith=f'REC-{ano}-')
            .order_by('-numero_recibo')
            .first()
        )
        if ultimo and ultimo.numero_recibo:
            try:
                seq = int(ultimo.numero_recibo.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'REC-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_valor = Decimal('0')
        old_estado = None

        if not is_new:
            old_self = ReciboCliente.objects.get(pk=self.pk)
            old_valor = old_self.valor_recebido
            old_estado = old_self.estado

        if not self.numero_recibo:
            self.numero_recibo = self._gerar_numero_recibo()

        super().save(*args, **kwargs)

        # Atualiza o valor pago na fatura associada (exclui recibos cancelados)
        # Usa select_for_update para evitar race conditions com saves concorrentes
        with transaction.atomic():
            factura = FacturaCliente.objects.select_for_update().get(pk=self.factura_id)
            old_estado_factura = factura.estado
            old_valor_pago = factura.valor_pago
            total_pago = factura.recibos.filter(factura=factura).exclude(estado='Cancelado').aggregate(
                total=models.Sum('valor_recebido'))['total'] or Decimal('0')
            total_pago += factura.facturas_recibo.filter(factura=factura, estado='Paga').aggregate(
                total=models.Sum('valor'))['total'] or Decimal('0')
            factura.valor_pago = total_pago
            if factura.valor_pago >= factura.valor_total:
                factura.estado = 'Paga'
            elif factura.valor_pago > 0:
                factura.estado = 'Parcialmente Paga'
            else:
                factura.estado = 'Pendente'
            factura.save(update_fields=['valor_pago', 'estado'])

            # Regista historico da factura se houve alteração de estado
            if old_estado_factura != factura.estado or old_valor_pago != factura.valor_pago:
                registrar_historico(
                    'Factura', factura.pk, factura.numero_factura, 'Pagamento recebido',
                    estado_anterior=old_estado_factura, estado_novo=factura.estado,
                    valor=self.valor_recebido,
                    utilizador_id=self.utilizador_responsavel_id, utilizador_nome=self.utilizador_responsavel_nome,
                    cliente_nome=factura.cliente.nome,
                    banca_id=self.banca_id, filial_id=self.filial_id,
                )

            cliente = Cliente.objects.select_for_update().get(pk=self.cliente.pk)
            novo_valor = self.valor_recebido if self.estado != 'Cancelado' else Decimal('0')
            antigo_valor = old_valor if old_estado != 'Cancelado' else Decimal('0')
            diff = novo_valor - antigo_valor
            if diff != 0:
                cliente.saldo_conta_corrente += diff
                cliente.save(update_fields=['saldo_conta_corrente'])
            self.cliente.refresh_from_db()

            # Nota: RequisicaoFundo é uma Fatura Pró-forma (proposta comercial).
            # Pagamentos são registados apenas contra a FacturaCliente (Fatura Final).
            # O campo requisicao_fundo em ReciboCliente é mantido apenas para
            # compatibilidade com dados legados; não actualiza estado/valor_pago da RF.

    @property
    def editavel(self):
        return self.estado != 'Cancelado'

    def __str__(self):
        return f"Recibo {self.numero_recibo} - {self.cliente.nome} - {self.valor_recebido}"


class NotaCredito(models.Model):
    """Modelo para Notas de Crédito de Clientes"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovada', 'Aprovada'),
        ('Rejeitada', 'Rejeitada'),
        ('Cancelada', 'Cancelada'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='notas_credito',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='notas_credito')
    numero_nota = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Nota')
    factura_relacionada = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='notas_credito', verbose_name='Factura Relacionada')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='notas_credito', verbose_name='Cliente')
    valor_creditado = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Creditado')
    motivo = models.CharField(max_length=255, verbose_name='Motivo')
    data = models.DateField(verbose_name='Data', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True, verbose_name='Estado')
    
    utilizador_criador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador')
    utilizador_criador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')
    utilizador_aprovador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    utilizador_aprovador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação', db_index=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Aprovação')

    class Meta:
        db_table = 'financeiro_nota_credito'
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'
        ordering = ['-data_criacao']
        indexes = [
            models.Index(fields=['cliente', 'data', 'estado'], name='ix_nc_cliente_data_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_nc_banca_filial'),
        ]

    def clean(self):
        if self.data and self.data > timezone.now().date():
            raise ValidationError({'data': 'A data não pode estar no futuro.'})

    def _gerar_numero_nota(self):
        """Gera número sequencial: NC-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            NotaCredito.objects
            .filter(numero_nota__startswith=f'NC-{ano}-')
            .order_by('-numero_nota')
            .first()
        )
        if ultimo and ultimo.numero_nota:
            try:
                seq = int(ultimo.numero_nota.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'NC-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_valor = Decimal('0')
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = NotaCredito.objects.get(pk=self.pk)
            old_valor = old_self.valor_creditado
            old_estado = old_self.estado

        if not self.numero_nota:
            self.numero_nota = self._gerar_numero_nota()

        super().save(*args, **kwargs)

        with transaction.atomic():
            novo_credito = self.valor_creditado if self.estado == 'Aprovada' else Decimal('0')
            antigo_credito = old_valor if old_estado == 'Aprovada' else Decimal('0')
            diff = novo_credito - antigo_credito
            if diff != 0:
                cliente = Cliente.objects.select_for_update().get(pk=self.cliente.pk)
                cliente.saldo_conta_corrente += diff
                cliente.save(update_fields=['saldo_conta_corrente'])
                self.cliente.refresh_from_db()
                num_factura = FacturaCliente.objects.filter(pk=self.factura_relacionada_id).values_list('numero_factura', flat=True).first() or ''
                registrar_historico(
                    'Factura', self.factura_relacionada_id, num_factura,
                    'Ajuste por Nota de Crédito', valor=self.valor_creditado,
                    utilizador_id=self.utilizador_aprovador_id or self.utilizador_criador_id,
                    utilizador_nome=self.utilizador_aprovador_nome or self.utilizador_criador_nome,
                    cliente_nome=self.cliente.nome,
                    banca_id=self.banca_id, filial_id=self.filial_id,
                )

    def __str__(self):
        return f"Nota Crédito {self.numero_nota} - {self.cliente.nome} - {self.valor_creditado}"


class NotaDebito(models.Model):
    """Modelo para Notas de Débito de Clientes"""

    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovada', 'Aprovada'),
        ('Rejeitada', 'Rejeitada'),
        ('Cancelada', 'Cancelada'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='notas_debito',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='notas_debito')
    numero_nota = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Nota')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='notas_debito', verbose_name='Cliente')
    factura_relacionada = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='notas_debito', verbose_name='Factura Relacionada')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor')
    motivo = models.CharField(max_length=255, verbose_name='Motivo')
    data = models.DateField(verbose_name='Data', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True, verbose_name='Estado')
    
    utilizador_criador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador')
    utilizador_criador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')
    utilizador_aprovador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    utilizador_aprovador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação', db_index=True)
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Aprovação')

    class Meta:
        db_table = 'financeiro_nota_debito'
        verbose_name = 'Nota de Débito'
        verbose_name_plural = 'Notas de Débito'
        ordering = ['-data_criacao']
        indexes = [
            models.Index(fields=['cliente', 'data', 'estado'], name='ix_nd_cliente_data_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_nd_banca_filial'),
        ]

    def clean(self):
        if self.data and self.data > timezone.now().date():
            raise ValidationError({'data': 'A data não pode estar no futuro.'})

    def _gerar_numero_nota(self):
        """Gera número sequencial: ND-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            NotaDebito.objects
            .filter(numero_nota__startswith=f'ND-{ano}-')
            .order_by('-numero_nota')
            .first()
        )
        if ultimo and ultimo.numero_nota:
            try:
                seq = int(ultimo.numero_nota.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'ND-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_valor = Decimal('0')
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = NotaDebito.objects.get(pk=self.pk)
            old_valor = old_self.valor
            old_estado = old_self.estado

        if not self.numero_nota:
            self.numero_nota = self._gerar_numero_nota()

        super().save(*args, **kwargs)

        with transaction.atomic():
            novo_debito = self.valor if self.estado == 'Aprovada' else Decimal('0')
            antigo_debito = old_valor if old_estado == 'Aprovada' else Decimal('0')
            diff = novo_debito - antigo_debito
            if diff != 0:
                cliente = Cliente.objects.select_for_update().get(pk=self.cliente.pk)
                cliente.saldo_conta_corrente -= diff
                cliente.save(update_fields=['saldo_conta_corrente'])
                self.cliente.refresh_from_db()
                num_factura = FacturaCliente.objects.filter(pk=self.factura_relacionada_id).values_list('numero_factura', flat=True).first() or ''
                registrar_historico(
                    'Factura', self.factura_relacionada_id, num_factura,
                    'Ajuste por Nota de Débito', valor=self.valor,
                    utilizador_id=self.utilizador_aprovador_id or self.utilizador_criador_id,
                    utilizador_nome=self.utilizador_aprovador_nome or self.utilizador_criador_nome,
                    cliente_nome=self.cliente.nome,
                    banca_id=self.banca_id, filial_id=self.filial_id,
                )

    def __str__(self):
        return f"Nota Débito {self.numero_nota} - {self.cliente.nome} - {self.valor}"


class FacturaRecibo(models.Model):
    """Modelo para Facturas-Recibo de Clientes (Pagamento simultâneo com a factura)"""
    
    ESTADOS = [
        ('Paga', 'Paga'),
        ('Cancelada', 'Cancelada'),
    ]

    FORMAS_PAGAMENTO = [
        ('Transferência Bancária', 'Transferência Bancária'),
        ('Multicaixa', 'Multicaixa'),
        ('TPAs', 'TPAs'),
        ('Depósito Bancário', 'Depósito Bancário'),
        ('Numerário', 'Numerário'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='facturas_recibo',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='facturas_recibo')
    numero_factura_recibo = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Factura-Recibo')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='facturas_recibo', verbose_name='Cliente')
    factura = models.ForeignKey(FacturaCliente, null=True, blank=True, on_delete=models.SET_NULL, related_name='facturas_recibo', verbose_name='Factura Associada')
    requisicao_fundo = models.ForeignKey('RequisicaoFundo', null=True, blank=True, on_delete=models.SET_NULL, related_name='facturas_recibo', verbose_name='Requisição de Fundos')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor')
    forma_pagamento = models.CharField(max_length=50, choices=FORMAS_PAGAMENTO, verbose_name='Forma de Pagamento', db_index=True)
    data = models.DateField(verbose_name='Data', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Paga', db_index=True, verbose_name='Estado')
    
    utilizador_responsavel_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Responsável')
    utilizador_responsavel_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Responsável')
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação', db_index=True)

    class Meta:
        db_table = 'financeiro_factura_recibo'
        verbose_name = 'Factura-Recibo'
        verbose_name_plural = 'Facturas-Recibo'
        ordering = ['-data_criacao']
        indexes = [
            models.Index(fields=['cliente', 'estado'], name='ix_fr_cliente_estado'),
            models.Index(fields=['factura', 'estado'], name='ix_fr_factura_estado'),
            models.Index(fields=['banca', 'filial'], name='ix_fr_banca_filial'),
        ]

    def clean(self):
        if self.data and self.data > timezone.now().date():
            raise ValidationError({'data': 'A data não pode estar no futuro.'})

    def _gerar_numero_factura_recibo(self):
        """Gera número sequencial: FR-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            FacturaRecibo.objects
            .filter(numero_factura_recibo__startswith=f'FR-{ano}-')
            .order_by('-numero_factura_recibo')
            .first()
        )
        if ultimo and ultimo.numero_factura_recibo:
            try:
                seq = int(ultimo.numero_factura_recibo.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'FR-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_valor = Decimal('0')
        old_estado = 'Paga'
        old_factura_pk = None
        
        if not is_new:
            old_self = FacturaRecibo.objects.get(pk=self.pk)
            old_valor = old_self.valor
            old_estado = old_self.estado
            old_factura_pk = old_self.factura_id

        if not self.numero_factura_recibo:
            self.numero_factura_recibo = self._gerar_numero_factura_recibo()

        factura_pk_changed = old_factura_pk != self.factura_id
        super().save(*args, **kwargs)

        # Factura-Recibo tem impacto líquido ZERO na conta corrente quando está Paga
        # porque debita e credita o mesmo valor ao mesmo tempo.
        # Mas se for cancelada, precisamos retirar o impacto (que já era líquido zero).
        # Para fins de robustez, calculamos a mudança:
        # Se passar de Paga para Cancelada:
        # - Antes: debito de valor, credito de valor (saldo inalterado)
        # - Agora: sem debito, sem credito (saldo inalterado)
        # Portanto, saldo da conta corrente não muda.

        # Atualiza o valor pago na factura associada (se houver)
        if self.factura and self.estado == 'Paga':
            self._atualizar_factura_valor_pago()
        elif old_factura_pk and old_estado == 'Paga' and (self.estado == 'Cancelada' or factura_pk_changed):
            # Se a factura-recibo foi cancelada ou desvinculada, reverte o valor
            factura = FacturaCliente.objects.filter(pk=old_factura_pk).first()
            if factura:
                self._atualizar_factura_valor_pago_por_factura(factura)

    def _atualizar_factura_valor_pago(self):
        """Atualiza valor_pago e estado da factura associada e regista historico."""
        if not self.factura_id:
            return
        with transaction.atomic():
            factura = FacturaCliente.objects.select_for_update().get(pk=self.factura_id)
            old_estado = factura.estado
            old_valor_pago = factura.valor_pago
            total_pago = factura.recibos.filter(factura=factura).exclude(estado='Cancelado').aggregate(
                total=models.Sum('valor_recebido'))['total'] or Decimal('0')
            total_pago += factura.facturas_recibo.filter(factura=factura, estado='Paga').aggregate(
                total=models.Sum('valor'))['total'] or Decimal('0')
            factura.valor_pago = total_pago
            if factura.valor_pago >= factura.valor_total:
                factura.estado = 'Paga'
            elif factura.valor_pago > 0:
                factura.estado = 'Parcialmente Paga'
            else:
                factura.estado = 'Pendente'
            factura.save(update_fields=['valor_pago', 'estado'])
            if old_estado != factura.estado or old_valor_pago != factura.valor_pago:
                registrar_historico(
                    'Factura', factura.pk, factura.numero_factura, 'Pagamento via Factura-Recibo',
                    estado_anterior=old_estado, estado_novo=factura.estado,
                    valor=self.valor,
                    utilizador_id=self.utilizador_responsavel_id, utilizador_nome=self.utilizador_responsavel_nome,
                    cliente_nome=factura.cliente.nome,
                    banca_id=self.banca_id, filial_id=self.filial_id,
                )

    def _atualizar_factura_valor_pago_por_factura(self, factura):
        """Atualiza valor_pago e estado após cancelamento/desvinculação."""
        with transaction.atomic():
            factura = FacturaCliente.objects.select_for_update().get(pk=factura.pk)
            old_estado = factura.estado
            old_valor_pago = factura.valor_pago
            total_pago = factura.recibos.filter(factura=factura).exclude(estado='Cancelado').aggregate(
                total=models.Sum('valor_recebido'))['total'] or Decimal('0')
            total_pago += factura.facturas_recibo.filter(factura=factura, estado='Paga').aggregate(
                total=models.Sum('valor'))['total'] or Decimal('0')
            factura.valor_pago = total_pago
            if factura.valor_pago >= factura.valor_total:
                factura.estado = 'Paga'
            elif factura.valor_pago > 0:
                factura.estado = 'Parcialmente Paga'
            else:
                factura.estado = 'Pendente'
            factura.save(update_fields=['valor_pago', 'estado'])
            if old_estado != factura.estado or old_valor_pago != factura.valor_pago:
                registrar_historico(
                    'Factura', factura.pk, factura.numero_factura, 'Pagamento removido (cancelamento)',
                    estado_anterior=old_estado, estado_novo=factura.estado,
                    valor=factura.valor_pago - old_valor_pago,
                    utilizador_id=self.utilizador_responsavel_id, utilizador_nome=self.utilizador_responsavel_nome,
                    cliente_nome=factura.cliente.nome,
                    banca_id=factura.banca_id, filial_id=factura.filial_id,
                )

    @property
    def valor_iva(self):
        """Calcula IVA de 14% sobre o valor (se aplicável).
        ATENÇÃO: O campo `valor` já inclui IVA menos Retenção.
        Esta propriedade NÃO é usada nas views — existe apenas para referência."""
        return self.valor * Decimal('0.14')
    
    @property
    def valor_total(self):
        """Retorna valor total da factura-recibo (valor + IVA).
        ATENÇÃO: O campo `valor` já inclui IVA menos Retenção.
        Para o valor real use `self.valor`."""
        return self.valor + self.valor_iva

    def __str__(self):
        return f"Factura-Recibo {self.numero_factura_recibo} - {self.cliente.nome} - {self.valor}"


class HistoricoFinanceiro(models.Model):
    """Registo cronológico de ações em documentos financeiros"""

    TIPO_DOCUMENTO = [
        ('Requisicao', 'Requisição'),
        ('Factura', 'Factura'),
        ('Recibo', 'Recibo'),
        ('NotaCredito', 'Nota de Crédito'),
        ('NotaDebito', 'Nota de Débito'),
        ('FacturaRecibo', 'Factura-Recibo'),
    ]

    tipo_documento = models.CharField(max_length=20, choices=TIPO_DOCUMENTO, db_index=True, verbose_name='Tipo de Documento')
    documento_id = models.IntegerField(db_index=True, verbose_name='ID do Documento')
    documento_numero = models.CharField(max_length=50, verbose_name='Número do Documento')
    cliente_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Cliente')
    accao = models.CharField(max_length=50, verbose_name='Ação')
    estado_anterior = models.CharField(max_length=50, blank=True, default='', verbose_name='Estado Anterior')
    estado_novo = models.CharField(max_length=50, blank=True, default='', verbose_name='Estado Novo')
    valor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor')
    utilizador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Utilizador')
    utilizador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Utilizador')
    banca = models.ForeignKey('rh.Banca', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='historicos_financeiros', verbose_name='Banca')
    filial = models.ForeignKey('rh.FilialBanca', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='historicos_financeiros', verbose_name='Filial')
    data = models.DateTimeField(auto_now_add=True, verbose_name='Data/Hora', db_index=True)

    class Meta:
        db_table = 'financeiro_historico'
        verbose_name = 'Histórico Financeiro'
        verbose_name_plural = 'Históricos Financeiros'
        ordering = ['-data']

        indexes = [
            models.Index(fields=['tipo_documento', 'documento_id'], name='idx_historico_tipo_doc'),
        ]

def registrar_historico(tipo_documento, documento_id, documento_numero, accao,
                        estado_anterior='', estado_novo='', valor=None,
                        utilizador_id=None, utilizador_nome='', cliente_nome='',
                        banca_id=None, filial_id=None):
    HistoricoFinanceiro.objects.create(
        tipo_documento=tipo_documento,
        documento_id=documento_id,
        documento_numero=documento_numero,
        cliente_nome=cliente_nome,
        accao=accao,
        estado_anterior=estado_anterior,
        estado_novo=estado_novo,
        valor=valor,
        utilizador_id=utilizador_id,
        utilizador_nome=utilizador_nome,
        banca_id=banca_id,
        filial_id=filial_id,
    )

# Fim dos modelos existentes.
