from django.contrib import admin
from .models import (
    Assembleia, PautaVotacao, PresencaAssembleia,
    Procuracao, Voto, ManifestoIntegridade, AtaDigital, Notificacao,
    QuotaConfig, QuotaGerada, PagamentoQuota, EstadoFinanceiro,
    IsencaoMembro, CertidaoRegularidade, CarteiraProfissional,
    CategoriaMembro, TipoQuota, HistoricoQuota,
)

admin.site.register(Assembleia)
admin.site.register(PautaVotacao)
admin.site.register(PresencaAssembleia)
admin.site.register(Procuracao)
admin.site.register(Voto)
admin.site.register(ManifestoIntegridade)
admin.site.register(AtaDigital)
admin.site.register(Notificacao)

@admin.register(QuotaConfig)
class QuotaConfigAdmin(admin.ModelAdmin):
    list_display = ['tipo', 'categoria', 'ano', 'mes', 'valor', 'multa_percentual', 'dias_carencia', 'ativa']
    list_filter = ['ativa', 'ano', 'tipo', 'categoria']
    search_fields = ['ano', 'tipo__nome']

@admin.register(QuotaGerada)
class QuotaGeradaAdmin(admin.ModelAdmin):
    list_display = ['despachante', 'referencia', 'periodo', 'valor_original', 'valor_multa', 'valor_total', 'status', 'data_vencimento']
    list_filter = ['status', 'ano', 'mes', 'tipo']
    search_fields = ['despachante__nome', 'referencia', 'fatura_uuid']
    def periodo(self, obj):
        return f'{obj.mes:02d}/{obj.ano}' if obj.mes and obj.ano else str(obj.ano)

@admin.register(PagamentoQuota)
class PagamentoQuotaAdmin(admin.ModelAdmin):
    list_display = ['despachante', 'quota', 'metodo', 'valor_pago', 'status', 'data_pagamento']
    list_filter = ['status', 'metodo']

@admin.register(EstadoFinanceiro)
class EstadoFinanceiroAdmin(admin.ModelAdmin):
    list_display = ['despachante', 'estado', 'ultima_atualizacao']
    list_filter = ['estado']

@admin.register(IsencaoMembro)
class IsencaoMembroAdmin(admin.ModelAdmin):
    list_display = ['despachante', 'tipo_quota', 'data_inicio', 'data_fim', 'motivo']

@admin.register(HistoricoQuota)
class HistoricoQuotaAdmin(admin.ModelAdmin):
    list_display = ['membro', 'acao', 'quota', 'created_at']
    list_filter = ['acao', 'created_at']
    search_fields = ['membro__nome', 'descricao']
    readonly_fields = ['membro', 'quota', 'pagamento', 'acao', 'descricao', 'utilizador', 'ip', 'created_at']
