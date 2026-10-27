from django.db import models
from decimal import Decimal
from django.utils import timezone


# ─── ConfiguracaoFiscal ───────────────────────────────────────────────────────

class ConfiguracaoFiscal(models.Model):
    """
    AGT integration settings per banca/empresa.
    Stores API credentials and configuration for invoice submission to AGT.
    """
    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, 
                             related_name='configuracoes_fiscais',
                             verbose_name='Banca')
    nif_emitente = models.CharField(max_length=50, verbose_name='NIF do Emitente')
    integration_enabled = models.BooleanField(default=False, 
                                             verbose_name='Integração Ativada')
    api_endpoint = models.URLField(max_length=500, verbose_name='Endpoint da API')
    username = models.CharField(max_length=255, blank=True, default='',
                               verbose_name='Nome de Utilizador')
    password = models.CharField(max_length=255, blank=True, default='',
                               verbose_name='Palavra-passe')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True,
                                    verbose_name='Criado em')
    atualizado_em = models.DateTimeField(auto_now=True,
                                        verbose_name='Atualizado em')

    class Meta:
        db_table = 'agt_invoicing_configuracao_fiscal'
        verbose_name = 'Configuração Fiscal'
        verbose_name_plural = 'Configurações Fiscais'
        indexes = [
            models.Index(fields=['banca', 'nif_emitente'], 
                        name='ix_cf_banca_nif'),
        ]

    def __str__(self):
        return f"{self.banca.nome} — {self.nif_emitente}"


# ─── Fatura ───────────────────────────────────────────────────────────────────

class Fatura(models.Model):
    """
    Main invoice model tracking submission to AGT.
    Represents a fiscal document (invoice, credit note, etc.)
    """
    TIPOS_DOCUMENTO = [
        ('FACTURA', 'Fatura'),
        ('NOTA_CREDITO', 'Nota de Crédito'),
        ('NOTA_DEBITO', 'Nota de Débito'),
        ('RECIBO', 'Recibo'),
        ('GUIA_REMESSA', 'Guia de Remessa'),
    ]

    ESTADOS = [
        ('RASCUNHO', 'Rascunho'),
        ('PENDENTE_AGT', 'Pendente AGT'),
        ('EMITIDA', 'Emitida'),
        ('REJEITADA', 'Rejeitada'),
    ]

    AGT_STATUSES = [
        ('APROVADA', 'Aprovada'),
        ('REJEITADA', 'Rejeitada'),
        ('PENDENTE', 'Pendente'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE,
                             related_name='faturas_agt_invoicing',
                             verbose_name='Banca')
    numero = models.CharField(max_length=50, unique=True, db_index=True,
                             verbose_name='Número da Fatura')
    serie = models.CharField(max_length=10, blank=True, default='A',
                            verbose_name='Série')
    tipo_documento = models.CharField(max_length=50, choices=TIPOS_DOCUMENTO,
                                     default='FACTURA',
                                     verbose_name='Tipo de Documento')
    estado = models.CharField(max_length=20, choices=ESTADOS,
                             default='RASCUNHO', db_index=True,
                             verbose_name='Estado')
    cliente_designacao = models.CharField(max_length=255,
                                         verbose_name='Designação do Cliente')
    cliente_nif = models.CharField(max_length=50,
                                  verbose_name='NIF do Cliente')
    total = models.DecimalField(max_digits=15, decimal_places=2,
                               default=Decimal('0.00'),
                               verbose_name='Total')
    emitida_em = models.DateTimeField(null=True, blank=True,
                                     verbose_name='Emitida em')
    criada_em = models.DateTimeField(auto_now_add=True, db_index=True,
                                    verbose_name='Criada em')
    atualizada_em = models.DateTimeField(auto_now=True,
                                        verbose_name='Atualizada em')
    agt_request_id = models.CharField(max_length=100, unique=True, null=True,
                                     blank=True, db_index=True,
                                     verbose_name='ID do Pedido AGT')
    agt_status = models.CharField(max_length=20, null=True, blank=True,
                                 choices=AGT_STATUSES,
                                 verbose_name='Status AGT')
    agt_hash_validacao = models.CharField(max_length=255, null=True, 
                                         blank=True,
                                         verbose_name='Hash de Validação AGT')
    agt_processada_em = models.DateTimeField(null=True, blank=True,
                                            verbose_name='Processada por AGT em')
    agt_erros = models.JSONField(null=True, blank=True,
                                verbose_name='Erros do AGT')

    class Meta:
        db_table = 'agt_invoicing_fatura'
        verbose_name = 'Fatura'
        verbose_name_plural = 'Faturas'
        indexes = [
            models.Index(fields=['banca', 'estado'], name='ix_fatura_banca_estado'),
            models.Index(fields=['banca', 'agt_status'], name='ix_fatura_banca_agt_status'),
            models.Index(fields=['agt_request_id'], name='ix_fatura_agt_request_id'),
        ]

    def __str__(self):
        return f"{self.numero} — {self.cliente_nif} — {self.estado}"


# ─── SubmissaoAgt ─────────────────────────────────────────────────────────────

class SubmissaoAgt(models.Model):
    """
    Submission queue and history for each invoice to AGT.
    Tracks submission attempts, retries, and current state.
    """
    ESTADOS = [
        ('PENDENTE', 'Pendente'),
        ('ACEITE', 'Aceite'),
        ('REJEITADA', 'Rejeitada'),
        ('FALHA_TEMPORARIA', 'Falha Temporária'),
        ('FALHA_PERMANENTE', 'Falha Permanente'),
        ('NAO_SUBMETIDA', 'Não Submetida'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE,
                             related_name='submissoes_agt_invoicing',
                             verbose_name='Banca')
    fatura = models.ForeignKey(Fatura, on_delete=models.PROTECT,
                              related_name='submissoes',
                              verbose_name='Fatura')
    estado = models.CharField(max_length=30, choices=ESTADOS,
                             default='PENDENTE', db_index=True,
                             verbose_name='Estado')
    payload_xml = models.TextField(blank=True, default='',
                                  verbose_name='Payload XML')
    submetida_em = models.DateTimeField(null=True, blank=True,
                                       verbose_name='Submetida em')
    ultima_tentativa_em = models.DateTimeField(null=True, blank=True,
                                              verbose_name='Última Tentativa em')
    proxima_tentativa_em = models.DateTimeField(null=True, blank=True,
                                               db_index=True,
                                               verbose_name='Próxima Tentativa em')
    tentativas = models.PositiveIntegerField(default=0,
                                            verbose_name='Tentativas')
    mensagem = models.TextField(blank=True, default='',
                               verbose_name='Mensagem')
    codigo_controlo = models.CharField(max_length=50, blank=True, default='',
                                      verbose_name='Código de Controlo')

    class Meta:
        db_table = 'agt_invoicing_submissao_agt'
        verbose_name = 'Submissão AGT'
        verbose_name_plural = 'Submissões AGT'
        indexes = [
            models.Index(fields=['fatura', 'estado'], name='ix_submissao_fatura_estado'),
            models.Index(fields=['proxima_tentativa_em'], name='ix_submissao_proxima_tentativa'),
        ]

    def __str__(self):
        return f"Submissão {self.pk} — Fatura {self.fatura.numero} — {self.estado}"


# ─── RegistoAuditoria ────────────────────────────────────────────────────────

class RegistoAuditoria(models.Model):
    """
    Full audit trail of all operations on invoices and submissions.
    """
    ACOES = [
        ('CREATED', 'Criada'),
        ('UPDATED', 'Atualizada'),
        ('SUBMITTED', 'Submetida'),
        ('APPROVED', 'Aprovada'),
        ('REJECTED', 'Rejeitada'),
        ('RETRIED', 'Retentada'),
        ('DELETED', 'Eliminada'),
    ]

    ORIGINS = [
        ('API', 'API'),
        ('SISTEMA_AGT', 'Sistema AGT'),
        ('ADMIN', 'Administrador'),
        ('WEBHOOK', 'Webhook'),
    ]

    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE,
                             related_name='registos_auditoria_agt_invoicing',
                             verbose_name='Banca')
    acao = models.CharField(max_length=50, choices=ACOES,
                           verbose_name='Ação')
    origin_tipo = models.CharField(max_length=30, choices=ORIGINS,
                                  verbose_name='Origem')
    entity_tipo = models.CharField(max_length=50,
                                  verbose_name='Tipo de Entidade')
    entity_id = models.IntegerField(verbose_name='ID da Entidade')
    motivo = models.TextField(blank=True, default='',
                             verbose_name='Motivo')
    ip_address = models.CharField(max_length=45, blank=True, default='',
                                 verbose_name='Endereço IP')
    user_agent = models.CharField(max_length=255, blank=True, default='',
                                 verbose_name='User Agent')
    usuario_id = models.IntegerField(null=True, blank=True,
                                    verbose_name='ID do Utilizador')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True,
                                    verbose_name='Criado em')

    class Meta:
        db_table = 'agt_invoicing_registo_auditoria'
        verbose_name = 'Registo de Auditoria'
        verbose_name_plural = 'Registos de Auditoria'
        indexes = [
            models.Index(fields=['criado_em', 'origin_tipo'], name='ix_auditoria_criado_origin'),
            models.Index(fields=['entity_tipo', 'entity_id'], name='ix_auditoria_entity'),
        ]

    def __str__(self):
        timestamp = self.criado_em.strftime('%Y-%m-%d %H:%M:%S') if self.criado_em else 'N/A'
        return f"{self.acao} — {self.entity_tipo}({self.entity_id}) — {timestamp}"
