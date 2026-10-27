from django.contrib import admin
from .models import ConfiguracaoFiscal, Fatura, SubmissaoAgt, RegistoAuditoria


@admin.register(ConfiguracaoFiscal)
class ConfiguracaoFiscalAdmin(admin.ModelAdmin):
    list_display = ('banca', 'nif_emitente', 'integration_enabled', 'criado_em')
    list_filter = ('integration_enabled', 'criado_em')
    search_fields = ('banca__nome', 'nif_emitente')
    readonly_fields = ('criado_em', 'atualizado_em')


@admin.register(Fatura)
class FaturaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'banca', 'estado', 'cliente_nif', 'total', 'criada_em')
    list_filter = ('estado', 'agt_status', 'tipo_documento', 'criada_em')
    search_fields = ('numero', 'cliente_nif', 'cliente_designacao', 'agt_request_id')
    readonly_fields = ('criada_em', 'atualizada_em', 'agt_request_id')


@admin.register(SubmissaoAgt)
class SubmissaoAgtAdmin(admin.ModelAdmin):
    list_display = ('fatura', 'estado', 'tentativas', 'ultima_tentativa_em', 'proxima_tentativa_em')
    list_filter = ('estado', 'ultima_tentativa_em', 'proxima_tentativa_em')
    search_fields = ('fatura__numero', 'codigo_controlo')
    readonly_fields = ('fatura',)


@admin.register(RegistoAuditoria)
class RegistoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('acao', 'entity_tipo', 'entity_id', 'origin_tipo', 'usuario_id', 'criado_em')
    list_filter = ('acao', 'origin_tipo', 'entity_tipo', 'criado_em')
    search_fields = ('entity_tipo', 'motivo', 'ip_address')
    readonly_fields = ('criado_em',)
