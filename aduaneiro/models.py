"""Modelos da app aduaneiro — mapeados para a tabela existente no MySQL."""
import json
import uuid as _uuid

from django.db import models


class DeclaracaoUnica(models.Model):
    """
    Declaração Única (DU).
    Mapeada para a tabela `declaracoes_unicas` já existente no MySQL.
    Campos extra (uuid, ref_despachante, dados_json, totais detalhados)
    são adicionados via migração ALTER TABLE.
    """

    STATUS_CHOICES = [
        ('Rascunho',   'Rascunho'),
        ('Submetida',  'Submetida'),
        ('Em Análise', 'Em Análise'),
        ('Aprovada',   'Aprovada'),
        ('Rejeitada',  'Rejeitada'),
    ]

    # ── Campos originais da tabela ────────────────────────────────────────────
    numero_du            = models.CharField(max_length=50, blank=True, null=True, unique=True)
    processo_id          = models.IntegerField(null=True, blank=True)   # FK removida — DU pode existir sem processo
    nif_declarante       = models.CharField(max_length=50, blank=True, default='')
    nome_declarante      = models.CharField(max_length=200, blank=True, default='')
    endereco_declarante  = models.TextField(blank=True, null=True)
    regime_aduaneiro     = models.CharField(max_length=100, blank=True, default='')
    codigo_pautal        = models.CharField(max_length=20, blank=True, default='')
    descricao_mercadoria = models.TextField(blank=True, null=True)
    quantidade           = models.IntegerField(default=0)
    peso_bruto           = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    peso_liquido         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_fob            = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_frete          = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    valor_seguro         = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    valor_cif            = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    direitos_aduaneiros  = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    iva                  = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    imposto_consumo      = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    emolumentos          = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    total_impostos       = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True)
    pais_origem          = models.CharField(max_length=100, blank=True, null=True)
    porto_embarque       = models.CharField(max_length=100, blank=True, null=True)
    porto_desembarque    = models.CharField(max_length=100, blank=True, null=True)
    meio_transporte      = models.CharField(max_length=50, blank=True, null=True)
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Rascunho', db_index=True)
    data_submissao       = models.DateTimeField(null=True, blank=True, db_index=True)
    data_aprovacao       = models.DateTimeField(null=True, blank=True)
    usuario_id           = models.IntegerField(db_index=True)
    created_at           = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at           = models.DateTimeField(auto_now=True)

    # ── Campos adicionados via migração ───────────────────────────────────────
    du_uuid           = models.CharField(max_length=36, blank=True, default='', db_index=True, db_column='du_uuid')
    codigo_processo   = models.CharField(max_length=8, blank=True, null=True, unique=True)  # 8 dígitos, único, gerado automaticamente
    ref_despachante   = models.CharField(max_length=100, blank=True, default='')
    exportador_nome  = models.CharField(max_length=200, blank=True, default='')
    destinatario_nome = models.CharField(max_length=200, blank=True, default='')
    total_derimp     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_iec        = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_emgead     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_direxp     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_iva        = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_geral      = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    dados_json       = models.TextField(default='{}')

    class Meta:
        db_table = 'declaracoes_unicas'
        managed  = True
        ordering = ['-created_at']
        verbose_name = 'Declaração Única'
        verbose_name_plural = 'Declarações Únicas'
        indexes = [
            models.Index(fields=['status', '-created_at'], name='ix_du_status_data'),
            models.Index(fields=['usuario_id', '-created_at'], name='ix_du_usuario_data'),
        ]

    def __str__(self):
        return self.numero_du or f'DU-{self.id}'

    # ── Helpers ───────────────────────────────────────────────────────────────

    def get_dados(self):
        try:
            return json.loads(self.dados_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_dados(self, dados: dict):
        self.dados_json = json.dumps(dados, ensure_ascii=False)

    def gerar_numero(self):
        """Gera número sequencial: DU-AAAA-NNNNNN."""
        from django.utils import timezone
        ano = timezone.now().year
        ultimo = (
            DeclaracaoUnica.objects
            .filter(numero_du__startswith=f'DU-{ano}-')
            .order_by('-numero_du')
            .first()
        )
        if ultimo and ultimo.numero_du:
            try:
                seq = int(ultimo.numero_du.split('-')[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'DU-{ano}-{seq:06d}'

    @staticmethod
    def gerar_codigo_processo():
        """Gera um código de processo único de 8 dígitos numéricos."""
        import random
        for _ in range(20):  # até 20 tentativas
            codigo = f'{random.randint(10000000, 99999999)}'
            if not DeclaracaoUnica.objects.filter(codigo_processo=codigo).exists():
                return codigo
        # Fallback: usar timestamp + random
        import time
        return str(int(time.time()))[-8:]

    def get_status_display_pt(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
