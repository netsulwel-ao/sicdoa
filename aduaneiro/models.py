"""Modelos da app aduaneiro — mapeados para a tabela existente no MySQL."""
import json
import uuid as _uuid

from django.db import models
from django.utils import timezone


class DeclaracaoUnica(models.Model):
    banca = models.ForeignKey('rh.Banca', on_delete=models.CASCADE, related_name='declaracoes',
                               null=True, blank=True)
    filial = models.ForeignKey('rh.FilialBanca', on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='declaracoes')
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
        ('Finalizada', 'Finalizada'),
    ]

    REGIME_CHOICES = [
        ('IM4', 'IM4 - Importação definitiva'),
        ('IM5', 'IM5 - Importação temporária'),
        ('IM6', 'IM6 - Reimportação'),
        ('IM7', 'IM7 - Armazenagem'),
        ('IM8', 'IM8 - Trânsito e Transbordo'),
        ('IMS4', 'IMS4 - Importação definitiva simplificada'),
        ('IMS5', 'IMS5 - Importação temporária simplificada'),
        ('IMS6', 'IMS6 - Reimportação simplificada'),
        ('IMS7', 'IMS7 - Armazenagem simplificada'),
        ('IMS8', 'IMS8 - Trânsito e Transbordo simplificado'),
        ('IMV4', 'IMV4 - Importação definitiva verbal'),
        ('IMV5', 'IMV5 - Importação temporária verbal'),
        ('IMV6', 'IMV6 - Reimportação verbal'),
        ('IMV7', 'IMV7 - Armazenagem verbal'),
        ('IMV8', 'IMV8 - Trânsito e Transbordo verbal'),
        ('EX1', 'EX1 - Exportação definitiva'),
        ('EX2', 'EX2 - Exportação temporária'),
        ('EX3', 'EX3 - Reexportação'),
        ('EXS1', 'EXS1 - Exportação definitiva simplificada'),
        ('EXS2', 'EXS2 - Exportação temporária simplificada'),
        ('EXS3', 'EXS3 - Reexportação simplificada'),
        ('EXV1', 'EXV1 - Exportação definitiva verbal'),
        ('EXV2', 'EXV2 - Exportação temporária verbal'),
        ('EXV3', 'EXV3 - Reexportação verbal'),
    ]

    # ── Campos originais da tabela ────────────────────────────────────────────
    numero_du            = models.CharField(max_length=50, blank=True, default='', null=True, unique=True)
    processo_id          = models.IntegerField(null=True, blank=True, db_index=True)   # FK removida — DU pode existir sem processo
    nif_declarante       = models.CharField(max_length=50, blank=True, default='', db_index=True)
    nome_declarante      = models.CharField(max_length=200, blank=True, default='', db_index=True)
    endereco_declarante  = models.TextField(blank=True, null=True)
    regime_aduaneiro     = models.CharField(max_length=100, blank=True, default='', db_index=True, choices=REGIME_CHOICES)
    codigo_pautal        = models.CharField(max_length=20, blank=True, default='', db_index=True)
    descricao_mercadoria = models.TextField(blank=True, null=True)
    quantidade           = models.IntegerField(default=0)
    peso_bruto           = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    peso_liquido         = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_fob            = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_frete          = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_seguro         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    valor_cif            = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    direitos_aduaneiros  = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    iva                  = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    imposto_consumo      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    emolumentos          = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_impostos       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    pais_origem          = models.CharField(max_length=100, blank=True, null=True, db_index=True)
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
    codigo_processo   = models.CharField(max_length=8, blank=True, default='', unique=True)  # 8 dígitos, único, gerado automaticamente
    ref_despachante   = models.CharField(max_length=100, blank=True, default='', db_index=True)
    exportador_nome  = models.CharField(max_length=200, blank=True, default='', db_index=True)
    destinatario_nome = models.CharField(max_length=200, blank=True, default='', db_index=True)
    total_derimp     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_iec        = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_emgead     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_direxp     = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_iva        = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_geral      = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    dados_json       = models.TextField(default='{}')
    nome_banco      = models.CharField(max_length=50, blank=True, default='')
    termo_pagamento = models.CharField(max_length=5, blank=True, default='')

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

    @property
    def partido_principal(self):
        """Retorna o partido principal da DU baseado no regime aduaneiro.
        Importação → Destinatário (quem recebe a mercadoria).
        Exportação → Exportador (quem envia a mercadoria).
        """
        regime = (self.regime_aduaneiro or '').strip()
        if regime.startswith('IM'):
            return {
                'tipo': 'Destinatário',
                'nome': self.destinatario_nome or '',
                'nif': (self.get_dados() or {}).get('destinatario_nif', ''),
            }
        return {
            'tipo': 'Exportador',
            'nome': self.exportador_nome or '',
            'nif': self.nif_declarante or '',
        }

    @property
    def label_regime(self):
        """Retorna o rótulo do regime para exibição."""
        regime = (self.regime_aduaneiro or '').strip()
        if regime.startswith('IM'):
            return 'Importação'
        elif regime.startswith('EX'):
            return 'Exportação'
        return regime

    def get_dados(self):
        try:
            return json.loads(self.dados_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_dados(self, dados: dict):
        self.dados_json = json.dumps(dados, ensure_ascii=False)

    def registrar_versao(self, campos_alterados, utilizador_id=None, utilizador_nome='', request=None):
        """Regista uma versão/histórico das alterações desta DU."""
        if request:
            utilizador_id = request.session.get('usuario_id')
            u = request.session.get('usuario', {})
            utilizador_nome = u.get('nome', '')
        HistoricoDU.objects.create(
            du=self,
            dados_json=self.dados_json,
            status=self.status,
            numero_du=self.numero_du,
            codigo_processo=self.codigo_processo,
            campos_alterados=campos_alterados,
            utilizador_id=utilizador_id,
            utilizador_nome=utilizador_nome,
        )

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


class HistoricoDU(models.Model):
    """Registo de versões/histórico de alterações da Declaração Única."""
    du = models.ForeignKey(DeclaracaoUnica, on_delete=models.CASCADE, related_name='historico_versoes')
    dados_json = models.TextField(verbose_name='Dados Completos (snapshot)')
    status = models.CharField(max_length=20, blank=True, default='', db_index=True, verbose_name='Estado')
    numero_du = models.CharField(max_length=50, blank=True, default='', verbose_name='Número DU')
    codigo_processo = models.CharField(max_length=8, blank=True, default='', verbose_name='Código Processo')
    campos_alterados = models.TextField(blank=True, default='', verbose_name='Campos Alterados (JSON)')
    utilizador_id = models.IntegerField(null=True, blank=True, verbose_name='ID do Utilizador')
    utilizador_nome = models.CharField(max_length=255, blank=True, default='', verbose_name='Nome do Utilizador')
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Data/Hora')

    class Meta:
        db_table = 'aduaneiro_historico_du'
        ordering = ['-criado_em']
        verbose_name = 'Histórico de DU'
        verbose_name_plural = 'Históricos de DU'
        indexes = [
            models.Index(fields=['du', '-criado_em'], name='ix_historico_du_data'),
        ]

    def __str__(self):
        return f'DU {self.numero_du or self.du_id} — {self.criado_em:%d/%m/%Y %H:%M}'

    def get_dados(self):
        try:
            return json.loads(self.dados_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_campos_alterados_dict(self):
        try:
            return json.loads(self.campos_alterados or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}


