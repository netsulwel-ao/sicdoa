from django.db import models
from django.db.models import F as ModelF
from django.conf import settings
from django.utils import timezone
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica

class RequisicaoFundo(models.Model):
    """Modelo para Requisição de Fundos para processos aduaneiros"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Em Aprovação', 'Em Aprovação'),
        ('Aprovada', 'Aprovada'),
        ('Rejeitada', 'Rejeitada'),
        ('Cancelada', 'Cancelada'),
    ]

    numero_requisicao = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Requisição')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='requisicoes_fundos', verbose_name='Cliente')
    processo_aduaneiro = models.ForeignKey(DeclaracaoUnica, on_delete=models.CASCADE, related_name='requisicoes_fundos', verbose_name='Processo Aduaneiro')
    valor_solicitado = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Solicitado')
    justificacao = models.TextField(verbose_name='Justificação')
    data = models.DateTimeField(auto_now_add=True, verbose_name='Data')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', verbose_name='Estado')
    solicitante_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Solicitante')
    solicitante_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Solicitante')
    responsavel_aprovacao_id_usuario = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    responsavel_aprovacao_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    documento_justificativo = models.FileField(upload_to='requisicoes_fundos/', null=True, blank=True, verbose_name='Documento Justificativo')

    class Meta:
        db_table = 'financeiro_requisicao_fundo'
        verbose_name = 'Requisição de Fundo'
        verbose_name_plural = 'Requisições de Fundos'
        ordering = ['-data']

    def _gerar_numero_requisicao(self):
        """Gera número sequencial: REQ-AAAA-NNNN."""
        ano = timezone.now().year
        ultimo = (
            RequisicaoFundo.objects
            .filter(numero_requisicao__startswith=f'REQ-{ano}-')
            .order_by('-numero_requisicao')
            .first()
        )
        if ultimo and ultimo.numero_requisicao:
            try:
                seq = int(ultimo.numero_requisicao.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'REQ-{ano}-{seq:04d}'

    def save(self, *args, **kwargs):
        if not self.numero_requisicao:
            self.numero_requisicao = self._gerar_numero_requisicao()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Req {self.numero_requisicao} - {self.cliente.nome} - {self.valor_solicitado}"


class FacturaCliente(models.Model):
    """Modelo para Facturas Finais de Clientes"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Parcialmente Paga', 'Parcialmente Paga'),
        ('Paga', 'Paga'),
        ('Cancelada', 'Cancelada'),
    ]

    numero_factura = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Factura')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='facturas_cliente', verbose_name='Cliente')
    processo_aduaneiro = models.ForeignKey(DeclaracaoUnica, on_delete=models.SET_NULL, null=True, blank=True, related_name='facturas_cliente', verbose_name='Processo Aduaneiro')
    
    # Detalhes dos custos
    honorarios_despachante = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Honorários do Despachante')
    taxas_aduaneiras = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Taxas Aduaneiras')
    emolumentos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Emolumentos')
    despesas_operacionais = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Despesas Operacionais')
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='IVA')
    outros_encargos = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Outros Encargos')
    
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Total')
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='Valor Pago')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', verbose_name='Estado')
    data_emissao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Emissão')
    data_vencimento = models.DateField(verbose_name='Data de Vencimento')
    descricao = models.TextField(verbose_name='Descrição')
    
    criado_por_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador')
    criado_por_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')

    class Meta:
        db_table = 'financeiro_factura_cliente'
        verbose_name = 'Factura de Cliente'
        verbose_name_plural = 'Facturas de Clientes'
        ordering = ['-data_emissao']

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
        old_valor = 0.0
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = FacturaCliente.objects.get(pk=self.pk)
            old_valor = float(old_self.valor_total)
            old_estado = old_self.estado

        # Calcula o valor total com base nos componentes se não for preenchido ou se for atualizado
        self.valor_total = (
            self.honorarios_despachante + 
            self.taxas_aduaneiras + 
            self.emolumentos + 
            self.despesas_operacionais + 
            self.iva + 
            self.outros_encargos
        )

        if not self.numero_factura:
            self.numero_factura = self._gerar_numero_factura()

        super().save(*args, **kwargs)

        # Atualiza a conta corrente do cliente: faturas debitam a conta corrente
        # Se for cancelada, retiramos o débito
        novo_valor = 0.0 if self.estado == 'Cancelada' else float(self.valor_total)
        antigo_debito = 0.0 if old_estado == 'Cancelada' else old_valor
        
        diff = novo_valor - antigo_debito
        if diff != 0:
            Cliente.objects.filter(pk=self.cliente.pk).update(
                saldo_conta_corrente=models.F('saldo_conta_corrente') - diff
            )
            self.cliente.refresh_from_db()

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

    numero_recibo = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número do Recibo')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='recibos_cliente', verbose_name='Cliente')
    factura = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='recibos', verbose_name='Factura')
    valor_recebido = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Recebido')
    forma_pagamento = models.CharField(max_length=50, choices=FORMAS_PAGAMENTO, verbose_name='Forma de Pagamento')
    data_pagamento = models.DateField(verbose_name='Data do Pagamento')
    referencia_bancaria = models.CharField(max_length=100, blank=True, default='', verbose_name='Referência Bancária')
    
    utilizador_responsavel_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Responsável')
    utilizador_responsavel_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Responsável')
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')

    class Meta:
        db_table = 'financeiro_recibo_cliente'
        verbose_name = 'Recibo de Cliente'
        verbose_name_plural = 'Recibos de Clientes'
        ordering = ['-data_criacao']

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
        old_valor = 0.0
        
        if not is_new:
            old_self = ReciboCliente.objects.get(pk=self.pk)
            old_valor = float(old_self.valor_recebido)

        if not self.numero_recibo:
            self.numero_recibo = self._gerar_numero_recibo()

        super().save(*args, **kwargs)

        # Atualiza o valor pago na fatura associada
        factura = self.factura
        total_pago = float(factura.recibos.filter(factura=factura).aggregate(total=models.Sum('valor_recebido'))['total'] or 0.0)
        factura.valor_pago = total_pago
        if factura.valor_pago >= factura.valor_total:
            factura.estado = 'Paga'
        elif factura.valor_pago > 0:
            factura.estado = 'Parcialmente Paga'
        else:
            factura.estado = 'Pendente'
        factura.save(update_fields=['valor_pago', 'estado'])

        # Atualiza a conta corrente do cliente: recibos creditam a conta corrente (aumentam saldo)
        diff = float(self.valor_recebido) - old_valor
        if diff != 0:
            Cliente.objects.filter(pk=self.cliente.pk).update(
                saldo_conta_corrente=models.F('saldo_conta_corrente') + diff
            )
            self.cliente.refresh_from_db()

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

    numero_nota = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Nota')
    factura_relacionada = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='notas_credito', verbose_name='Factura Relacionada')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='notas_credito', verbose_name='Cliente')
    valor_creditado = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Creditado')
    motivo = models.CharField(max_length=255, verbose_name='Motivo')
    data = models.DateField(verbose_name='Data')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', verbose_name='Estado')
    
    utilizador_criador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador')
    utilizador_criador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')
    utilizador_aprovador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    utilizador_aprovador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Aprovação')

    class Meta:
        db_table = 'financeiro_nota_credito'
        verbose_name = 'Nota de Crédito'
        verbose_name_plural = 'Notas de Crédito'
        ordering = ['-data_criacao']

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
        old_valor = 0.0
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = NotaCredito.objects.get(pk=self.pk)
            old_valor = float(old_self.valor_creditado)
            old_estado = old_self.estado

        if not self.numero_nota:
            self.numero_nota = self._gerar_numero_nota()

        super().save(*args, **kwargs)

        # Atualiza conta corrente: nota de crédito Aprovada credita a conta corrente (aumenta o saldo)
        # Se mudar de Aprovada para outra coisa ou vice-versa, ajustamos.
        novo_credito = float(self.valor_creditado) if self.estado == 'Aprovada' else 0.0
        antigo_credito = old_valor if old_estado == 'Aprovada' else 0.0
        
        diff = novo_credito - antigo_credito
        if diff != 0:
            Cliente.objects.filter(pk=self.cliente.pk).update(
                saldo_conta_corrente=ModelF('saldo_conta_corrente') + diff
            )
            self.cliente.refresh_from_db()

        # Ajusta valor_total da factura relacionada (reduz quando aprovada)
        if diff != 0 and self.factura_relacionada_id:
            FacturaCliente.objects.filter(pk=self.factura_relacionada_id).update(
                valor_total=ModelF('valor_total') - diff
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

    numero_nota = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Nota')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='notas_debito', verbose_name='Cliente')
    factura_relacionada = models.ForeignKey(FacturaCliente, on_delete=models.CASCADE, related_name='notas_debito', verbose_name='Factura Relacionada')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor')
    motivo = models.CharField(max_length=255, verbose_name='Motivo')
    data = models.DateField(verbose_name='Data')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', verbose_name='Estado')
    
    utilizador_criador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador')
    utilizador_criador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')
    utilizador_aprovador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    utilizador_aprovador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')
    data_aprovacao = models.DateTimeField(null=True, blank=True, verbose_name='Data de Aprovação')

    class Meta:
        db_table = 'financeiro_nota_debito'
        verbose_name = 'Nota de Débito'
        verbose_name_plural = 'Notas de Débito'
        ordering = ['-data_criacao']

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
        old_valor = 0.0
        old_estado = 'Pendente'
        
        if not is_new:
            old_self = NotaDebito.objects.get(pk=self.pk)
            old_valor = float(old_self.valor)
            old_estado = old_self.estado

        if not self.numero_nota:
            self.numero_nota = self._gerar_numero_nota()

        super().save(*args, **kwargs)

        # Atualiza conta corrente: nota de débito Aprovada debita a conta corrente (diminui o saldo)
        # Se mudar de Aprovada para outra coisa ou vice-versa, ajustamos.
        novo_debito = float(self.valor) if self.estado == 'Aprovada' else 0.0
        antigo_debito = old_valor if old_estado == 'Aprovada' else 0.0
        
        diff = novo_debito - antigo_debito
        if diff != 0:
            Cliente.objects.filter(pk=self.cliente.pk).update(
                saldo_conta_corrente=ModelF('saldo_conta_corrente') - diff
            )
            self.cliente.refresh_from_db()

        # Ajusta valor_total da factura relacionada (aumenta quando aprovada)
        if diff != 0 and self.factura_relacionada_id:
            FacturaCliente.objects.filter(pk=self.factura_relacionada_id).update(
                valor_total=ModelF('valor_total') + diff
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

    numero_factura_recibo = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Factura-Recibo')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='facturas_recibo', verbose_name='Cliente')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor')
    forma_pagamento = models.CharField(max_length=50, choices=FORMAS_PAGAMENTO, verbose_name='Forma de Pagamento')
    data = models.DateField(verbose_name='Data')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Paga', verbose_name='Estado')
    
    utilizador_responsavel_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Responsável')
    utilizador_responsavel_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Responsável')
    data_criacao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Criação')

    class Meta:
        db_table = 'financeiro_factura_recibo'
        verbose_name = 'Factura-Recibo'
        verbose_name_plural = 'Facturas-Recibo'
        ordering = ['-data_criacao']

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
        old_valor = 0.0
        old_estado = 'Paga'
        
        if not is_new:
            old_self = FacturaRecibo.objects.get(pk=self.pk)
            old_valor = float(old_self.valor)
            old_estado = old_self.estado

        if not self.numero_factura_recibo:
            self.numero_factura_recibo = self._gerar_numero_factura_recibo()

        super().save(*args, **kwargs)

        # Factura-Recibo tem impacto líquido ZERO na conta corrente quando está Paga
        # porque debita e credita o mesmo valor ao mesmo tempo.
        # Mas se for cancelada, precisamos retirar o impacto (que já era líquido zero).
        # Para fins de robustez, calculamos a mudança:
        # Se passar de Paga para Cancelada:
        # - Antes: debito de valor, credito de valor (saldo inalterado)
        # - Agora: sem debito, sem credito (saldo inalterado)
        # Portanto, saldo da conta corrente não muda.

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

    tipo_documento = models.CharField(max_length=20, choices=TIPO_DOCUMENTO, verbose_name='Tipo de Documento')
    documento_id = models.IntegerField(verbose_name='ID do Documento')
    documento_numero = models.CharField(max_length=50, verbose_name='Número do Documento')
    cliente_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Cliente')
    accao = models.CharField(max_length=50, verbose_name='Ação')
    estado_anterior = models.CharField(max_length=50, blank=True, default='', verbose_name='Estado Anterior')
    estado_novo = models.CharField(max_length=50, blank=True, default='', verbose_name='Estado Novo')
    valor = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor')
    utilizador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Utilizador')
    utilizador_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Utilizador')
    data = models.DateTimeField(auto_now_add=True, verbose_name='Data/Hora')

    class Meta:
        db_table = 'financeiro_historico'
        verbose_name = 'Histórico Financeiro'
        verbose_name_plural = 'Históricos Financeiros'
        ordering = ['-data']


def registrar_historico(tipo_documento, documento_id, documento_numero, accao,
                        estado_anterior='', estado_novo='', valor=None,
                        utilizador_id=None, utilizador_nome='', cliente_nome=''):
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
    )
