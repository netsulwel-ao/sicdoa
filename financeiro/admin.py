from django.contrib import admin
from .models import (
    FacturaCliente, ReciboCliente, NotaCredito, NotaDebito, FacturaRecibo,
    RequisicaoFundo, RequisicaoFundoLinha
)


class RequisicaoFundoLinhaInline(admin.TabularInline):
    model = RequisicaoFundoLinha
    extra = 0
    fields = ('tipo_custo', 'descricao', 'documentada', 'despesa_tipo', 'valor', 'ordem')


@admin.register(RequisicaoFundo)
class RequisicaoFundoAdmin(admin.ModelAdmin):
    list_display = ('numero_requisicao', 'cliente', 'total_geral', 'estado', 'criado_por_nome', 'data_emissao')
    list_filter = ('estado', 'data_emissao', 'data_validade')
    search_fields = ('numero_requisicao', 'cliente__nome', 'criado_por_nome')
    readonly_fields = ('numero_requisicao', 'data_emissao', 'subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral')
    ordering = ('-data_emissao',)
    inlines = [RequisicaoFundoLinhaInline]
    fieldsets = (
        ('Documento', {'fields': ('numero_requisicao', 'data_emissao', 'data_validade', 'moeda_referencia', 'cambio_referencia')}),
        ('Cliente', {'fields': ('cliente', 'pessoa_contacto', 'processo_aduaneiro')}),
        ('Totalizações', {'fields': ('subtotal_geral', 'iva_honorarios', 'retencao', 'total_geral', 'valor_pago')}),
        ('Status', {'fields': ('estado',)}),
        ('Metadados', {'fields': ('criado_por_id', 'criado_por_nome', 'observacoes')}),
    )


@admin.register(RequisicaoFundoLinha)
class RequisicaoFundoLinhaAdmin(admin.ModelAdmin):
    list_display = ('requisicao', 'tipo_custo', 'descricao', 'valor', 'documentada')
    list_filter = ('tipo_custo', 'documentada')
    search_fields = ('requisicao__numero_requisicao', 'descricao')
    ordering = ('requisicao', 'ordem')


@admin.register(FacturaCliente)
class FacturaClienteAdmin(admin.ModelAdmin):
    list_display = ('numero_factura', 'cliente', 'valor_total', 'estado', 'criado_por_nome', 'data_emissao')
    list_filter = ('estado', 'data_emissao', 'data_vencimento')
    search_fields = ('numero_factura', 'cliente__nome', 'criado_por_nome')
    readonly_fields = ('numero_factura', 'data_emissao', 'valor_total')
    ordering = ('-data_emissao',)
    fieldsets = (
        ('Documento', {'fields': ('numero_factura', 'data_emissao', 'data_vencimento', 'descricao')}),
        ('Cliente', {'fields': ('cliente', 'processo_aduaneiro')}),
        ('Detalhes de Custos', {'fields': ('honorarios_despachante', 'taxas_aduaneiras', 'emolumentos', 'despesas_operacionais', 'iva', 'outros_encargos')}),
        ('Totalizações', {'fields': ('valor_total', 'valor_pago')}),
        ('Status', {'fields': ('estado',)}),
        ('Metadados', {'fields': ('criado_por_id', 'criado_por_nome')}),
    )

