from datetime import date as date_type
from decimal import Decimal

from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from django.core.exceptions import ValidationError
from clientes.models import Cliente
from aduaneiro.models import DeclaracaoUnica


class FluxoAprovacao(models.Model):
    nome = models.CharField(max_length=100, verbose_name='Nome do Fluxo', db_index=True)
    descricao = models.TextField(blank=True, default='', verbose_name='Descrição')
    banca = models.ForeignKey('rh.Banca', null=True, blank=True, on_delete=models.CASCADE,
                               related_name='fluxos_aprovacao', verbose_name='Banca')
    criado_por = models.ForeignKey(
        'users.Usuario', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Criado por'
    )
    criado_em = models.DateTimeField(auto_now_add=True, verbose_name='Criado em')
    ativo = models.BooleanField(default=True, verbose_name='Activo', db_index=True)

    class Meta:
        db_table = 'financeiro_fluxo_aprovacao'
        verbose_name = 'Fluxo de Aprovação'
        verbose_name_plural = 'Fluxos de Aprovação'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class NivelAprovacao(models.Model):
    fluxo = models.ForeignKey(
        FluxoAprovacao, on_delete=models.CASCADE,
        related_name='niveis', verbose_name='Fluxo'
    )
    banca = models.ForeignKey('rh.Banca', null=True, blank=True, on_delete=models.CASCADE,
                               related_name='niveis_aprovacao', verbose_name='Banca')
    ordem = models.PositiveSmallIntegerField(verbose_name='Ordem', db_index=True)
    nome = models.CharField(max_length=100, verbose_name='Nome do Nível', db_index=True)
    qtde_aprovadores = models.PositiveSmallIntegerField(
        default=1, verbose_name='Quantidade de Aprovadores Necessários'
    )
    funcao = models.ForeignKey(
        'users.Funcao', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='niveis_aprovacao', verbose_name='Função Aprovadora'
    )

    class Meta:
        db_table = 'financeiro_nivel_aprovacao'
        verbose_name = 'Nível de Aprovação'
        verbose_name_plural = 'Níveis de Aprovação'
        ordering = ['fluxo', 'ordem']
        unique_together = [['fluxo', 'ordem'], ['fluxo', 'funcao']]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.funcao_id is None:
            dupes = NivelAprovacao.objects.filter(
                fluxo=self.fluxo, funcao__isnull=True
            )
        else:
            dupes = NivelAprovacao.objects.filter(
                fluxo=self.fluxo, funcao=self.funcao
            )
        if self.pk:
            dupes = dupes.exclude(pk=self.pk)
        if dupes.exists():
            raise ValidationError('Já existe um nível com esta configuração.')

    def save(self, *args, **kwargs):
        if not kwargs.get('update_fields'):
            self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.fluxo.nome} — Nível {self.ordem}: {self.nome}'


class AprovacaoRequisicao(models.Model):
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Aprovada', 'Aprovada'),
        ('Rejeitada', 'Rejeitada'),
    ]

    requisicao = models.ForeignKey(
        'RequisicaoFundo', on_delete=models.CASCADE,
        related_name='aprovacoes', verbose_name='Requisição'
    )
    nivel = models.ForeignKey(
        NivelAprovacao, on_delete=models.CASCADE,
        related_name='aprovacoes', verbose_name='Nível'
    )
    aprovador = models.ForeignKey(
        'users.Usuario', on_delete=models.CASCADE,
        related_name='votos_aprovacao', verbose_name='Aprovador'
    )
    estado = models.CharField(
        max_length=20, choices=ESTADOS, default='Pendente',
        db_index=True, verbose_name='Estado'
    )
    observacao = models.TextField(blank=True, default='', verbose_name='Observação')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Criado em', db_index=True)
    respondida_em = models.DateTimeField(null=True, blank=True, verbose_name='Respondida em')

    class Meta:
        db_table = 'financeiro_aprovacao_requisicao'
        verbose_name = 'Aprovação de Requisição'
        verbose_name_plural = 'Aprovações de Requisições'
        ordering = ['nivel__ordem', 'created_at']
        unique_together = ['requisicao', 'nivel', 'aprovador']

    def __str__(self):
        return f'{self.requisicao.numero_requisicao} — {self.aprovador.nome} — {self.estado}'


class RequisicaoFundo(models.Model):
    """Modelo para Requisição de Fundos para processos aduaneiros"""
    
    ESTADOS = [
        ('Pendente', 'Pendente'),
        ('Em Aprovação', 'Em Aprovação'),
        ('Aprovada', 'Aprovada'),
        ('Rejeitada', 'Rejeitada'),
        ('Cancelada', 'Cancelada'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='requisicoes_fundo',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='requisicoes_fundo')
    numero_requisicao = models.CharField(max_length=50, unique=True, blank=True, verbose_name='Número da Requisição')
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='requisicoes_fundos', verbose_name='Cliente')
    processo_aduaneiro = models.ForeignKey(DeclaracaoUnica, on_delete=models.CASCADE, related_name='requisicoes_fundos', verbose_name='Processo Aduaneiro')
    valor_solicitado = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor Solicitado')
    justificacao = models.TextField(verbose_name='Justificação')
    data = models.DateTimeField(auto_now_add=True, verbose_name='Data', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True, verbose_name='Estado')
    solicitante_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Solicitante', db_index=True)
    solicitante_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Solicitante')
    responsavel_aprovacao_id_usuario = models.IntegerField(null=True, blank=True, verbose_name='ID do Aprovador')
    responsavel_aprovacao_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Aprovador')
    documento_justificativo = models.FileField(upload_to='requisicoes_fundos/', null=True, blank=True, verbose_name='Documento Justificativo')
    motivo_rejeicao = models.TextField(blank=True, default='', verbose_name='Motivo da Rejeição')
    fluxo_aprovacao = models.ForeignKey(
        FluxoAprovacao, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='requisicoes',
        verbose_name='Fluxo de Aprovação'
    )
    nivel_atual = models.PositiveSmallIntegerField(default=0, verbose_name='Nível Actual', db_index=True)

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

    @property
    def editavel(self):
        return self.estado == 'Pendente'

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

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='facturas_cliente',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='facturas_cliente')
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
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Pendente', db_index=True, verbose_name='Estado')
    data_emissao = models.DateTimeField(auto_now_add=True, verbose_name='Data de Emissão', db_index=True)
    data_vencimento = models.DateField(verbose_name='Data de Vencimento', db_index=True)
    descricao = models.TextField(verbose_name='Descrição')
    
    criado_por_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Criador', db_index=True)
    criado_por_nome = models.CharField(max_length=200, blank=True, default='', verbose_name='Nome do Criador')

    class Meta:
        db_table = 'financeiro_factura_cliente'
        verbose_name = 'Factura de Cliente'
        verbose_name_plural = 'Facturas de Clientes'
        ordering = ['-data_emissao']
        indexes = [
            models.Index(fields=['estado', '-data_emissao'], name='ix_factura_estado_data'),
        ]

    def clean(self):
        if self.data_vencimento and self.data_vencimento < timezone.now().date():
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
                self.outros_encargos
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
