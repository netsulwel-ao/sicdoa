from django.urls import path
from . import views
from . import views_contacorrente as cc
from . import views_relatorios as rel


app_name = 'financeiro'

urlpatterns = [
    # Requisições de Fundos
    path('requisicoes/', views.RequisicaoFundoListView.as_view(), name='requisicao_lista'),
    path('requisicoes/criar/', views.RequisicaoFundoCreateView.as_view(), name='requisicao_criar'),
    path('requisicoes/<int:pk>/', views.RequisicaoFundoDetailView.as_view(), name='requisicao_detalhe'),
    path('requisicoes/<int:pk>/editar/', views.RequisicaoFundoUpdateView.as_view(), name='requisicao_editar'),
    path('requisicoes/<int:pk>/cancelar/', views.cancelar_requisicao, name='requisicao_cancelar'),
    path('requisicoes/<int:pk>/eliminar/', views.eliminar_requisicao, name='requisicao_eliminar'),
    path('requisicoes/<int:pk>/aceitar/', views.aceitar_requisicao, name='requisicao_aceitar'),
    path('requisicoes/<int:pk>/rejeitar/', views.rejeitar_requisicao, name='requisicao_rejeitar'),
    path('requisicoes/<int:pk>/pdf/', views.requisicao_pdf, name='requisicao_pdf'),
    path('requisicoes/<int:pk>/enviar-email/', views.requisicao_enviar_email, name='requisicao_enviar_email'),
    path('requisicoes/<int:pk>/criar-factura/', views.criar_factura_de_requisicao, name='requisicao_criar_factura'),
    path('requisicoes/<int:pk>/criar-factura-recibo/', views.requisicao_criar_factura_recibo, name='requisicao_criar_factura_recibo'),
    path('requisicoes/<int:pk>/linha/adicionar/', views.adicionar_linha_requisicao, name='requisicao_linha_adicionar'),
    path('requisicoes/<int:pk>/linha/<int:linha_id>/editar/', views.editar_linha_requisicao, name='requisicao_linha_editar'),
    path('requisicoes/<int:pk>/linha/<int:linha_id>/eliminar/', views.eliminar_linha_requisicao, name='requisicao_linha_eliminar'),
    
    # APIs para Auto-preenchimento
    path('api/usuario-banca/', views.api_dados_usuario_banca, name='api_dados_usuario_banca'),
    path('api/buscar-cliente/', views.api_buscar_cliente, name='api_buscar_cliente'),
    path('api/dados-cliente/', views.api_dados_cliente, name='api_dados_cliente'),
    path('api/processos-cliente/', views.api_processos_cliente, name='api_processos_cliente'),
    path('api/dados-processo/', views.api_dados_processo, name='api_dados_processo'),
    path('api/facturas-por-cliente/', views.api_facturas_por_cliente, name='api_facturas_por_cliente'),

    # Facturas Finais
    path('facturas/', views.FacturaClienteListView.as_view(), name='factura_lista'),
    # ELIMINADO: Criacão apenas a partir da Requisição de Fundo (financeiro:requisicao_criar_factura)
    # path('facturas/criar/', views.FacturaClienteCreateView.as_view(), name='factura_criar'),
    path('facturas/<int:pk>/', views.FacturaClienteDetailView.as_view(), name='factura_detalhe'),
    path('facturas/<int:pk>/pdf/', views.factura_pdf, name='factura_pdf'),
    path('facturas/<int:pk>/editar/', views.FacturaClienteUpdateView.as_view(), name='factura_editar'),
    path('facturas/<int:pk>/cancelar/', views.cancelar_factura, name='factura_cancelar'),
    path('facturas/<int:pk>/eliminar/', views.eliminar_factura, name='factura_eliminar'),
    path('facturas/<int:pk>/enviar-email/', views.factura_enviar_email, name='factura_enviar_email'),
    path('facturas/du-custos/<int:pk>/', views.du_custos_json, name='factura_du_custos'),

    # Gestão de Recibos
    path('recibos/', views.ReciboClienteListView.as_view(), name='recibo_lista'),
    path('recibos/criar/', views.ReciboClienteCreateView.as_view(), name='recibo_criar'),
    path('recibos/<int:pk>/', views.ReciboClienteDetailView.as_view(), name='recibo_detalhe'),
    path('recibos/<int:pk>/pdf/', views.recibo_pdf, name='recibo_pdf'),
    path('recibos/<int:pk>/enviar-email/', views.recibo_enviar_email, name='recibo_enviar_email'),
    path('recibos/<int:pk>/editar/', views.editar_recibo, name='recibo_editar'),
    path('recibos/<int:pk>/cancelar/', views.cancelar_recibo, name='recibo_cancelar'),

    # Notas
    path('notas/', views.NotasHomeView.as_view(), name='notas_home'),

    # Notas de Crédito
    path('notas-credito/', views.NotaCreditoListView.as_view(), name='nota_credito_lista'),
    path('notas-credito/criar/', views.NotaCreditoCreateView.as_view(), name='nota_credito_criar'),
    path('notas-credito/<int:pk>/', views.NotaCreditoDetailView.as_view(), name='nota_credito_detalhe'),
    path('notas-credito/<int:pk>/editar/', views.NotaCreditoUpdateView.as_view(), name='nota_credito_editar'),
    path('notas-credito/<int:pk>/aprovar/', views.aprovar_nota_credito, name='nota_credito_aprovar'),
    path('notas-credito/<int:pk>/rejeitar/', views.rejeitar_nota_credito, name='nota_credito_rejeitar'),
    path('notas-credito/<int:pk>/cancelar/', views.cancelar_nota_credito, name='nota_credito_cancelar'),
    path('notas-credito/<int:pk>/pdf/', views.nota_credito_pdf, name='nota_credito_pdf'),
    path('notas-credito/<int:pk>/enviar-email/', views.nota_credito_enviar_email, name='nota_credito_enviar_email'),
    path('notas-credito/<int:pk>/eliminar/', views.eliminar_nota_credito, name='nota_credito_eliminar'),

    # Notas de Débito
    path('notas-debito/', views.NotaDebitoListView.as_view(), name='nota_debito_lista'),
    path('notas-debito/criar/', views.NotaDebitoCreateView.as_view(), name='nota_debito_criar'),
    path('notas-debito/<int:pk>/', views.NotaDebitoDetailView.as_view(), name='nota_debito_detalhe'),
    path('notas-debito/<int:pk>/editar/', views.NotaDebitoUpdateView.as_view(), name='nota_debito_editar'),
    path('notas-debito/<int:pk>/aprovar/', views.aprovar_nota_debito, name='nota_debito_aprovar'),
    path('notas-debito/<int:pk>/rejeitar/', views.rejeitar_nota_debito, name='nota_debito_rejeitar'),
    path('notas-debito/<int:pk>/cancelar/', views.cancelar_nota_debito, name='nota_debito_cancelar'),
    path('notas-debito/<int:pk>/eliminar/', views.eliminar_nota_debito, name='nota_debito_eliminar'),
    path('notas-debito/<int:pk>/pdf/', views.nota_debito_pdf, name='nota_debito_pdf'),
    path('notas-debito/<int:pk>/enviar-email/', views.nota_debito_enviar_email, name='nota_debito_enviar_email'),

    # Facturas
    path('facturas/home/', views.FacturasHomeView.as_view(), name='facturas_home'),

    # Facturas-Recibo
    path('facturas-recibo/', views.FacturaReciboListView.as_view(), name='factura_recibo_lista'),
    # ELIMINADO: Criacão apenas a partir da Requisição de Fundo
    # path('facturas-recibo/criar/', views.FacturaReciboCreateView.as_view(), name='factura_recibo_criar'),
    path('facturas-recibo/<int:pk>/', views.FacturaReciboDetailView.as_view(), name='factura_recibo_detalhe'),
    path('facturas-recibo/<int:pk>/pdf/', views.factura_recibo_pdf, name='factura_recibo_pdf'),
    path('facturas-recibo/<int:pk>/enviar-email/', views.factura_recibo_enviar_email, name='factura_recibo_enviar_email'),
    path('facturas-recibo/<int:pk>/editar/', views.FacturaReciboUpdateView.as_view(), name='factura_recibo_editar'),
    path('facturas-recibo/<int:pk>/cancelar/', views.cancelar_factura_recibo, name='factura_recibo_cancelar'),

    # ─── Conta Corrente ──────────────────────────────────────────────────
    path('conta-corrente/', cc.ContaCorrenteHomeView.as_view(), name='conta_corrente_home'),
    path('conta-corrente/cliente/<int:pk>/', cc.ContaCorrenteClienteView.as_view(), name='conta_corrente_cliente'),
    path('conta-corrente/cliente/', cc.ContaCorrenteClienteListView.as_view(), name='conta_corrente_cliente_lista'),
    path('conta-corrente/geral/', cc.ContaCorrenteGeralView.as_view(), name='conta_corrente_geral'),
    path('conta-corrente/mensal/', cc.ContaCorrenteMensalView.as_view(), name='conta_corrente_mensal'),
    path('conta-corrente/mensal/excel/', cc.conta_corrente_mensal_excel, name='conta_corrente_mensal_excel'),
    path('conta-corrente/mensal/pdf/', cc.conta_corrente_mensal_pdf, name='conta_corrente_mensal_pdf'),
    path('conta-corrente/periodica/', cc.ContaCorrentePeriodicaView.as_view(), name='conta_corrente_periodica'),
    path('conta-corrente/periodica/json/', cc.conta_corrente_periodica_json, name='conta_corrente_periodica_json'),
    path('conta-corrente/periodica/pdf/', cc.conta_corrente_periodica_pdf, name='conta_corrente_periodica_pdf'),
    path('conta-corrente/periodica/excel/', cc.conta_corrente_periodica_excel, name='conta_corrente_periodica_excel'),

    # ─── Relatórios Financeiros ────────────────────────────────────────────
    # Home
    path('relatorios/', rel.RelatorioHomeView.as_view(), name='relatorio_home'),
    # Operacionais
    path('relatorios/requisicao-fundos/', rel.RelatorioRequisicaoFundosView.as_view(), name='relatorio_requisicao_fundos'),
    path('relatorios/facturacao/', rel.RelatorioFacturacaoView.as_view(), name='relatorio_facturacao'),
    path('relatorios/recibos/', rel.RelatorioRecibosView.as_view(), name='relatorio_recibos'),
    path('relatorios/notas/', rel.RelatoriosNotasHomeView.as_view(), name='relatorio_notas_home'),
    path('relatorios/notas-credito/', rel.RelatorioNotasCreditoView.as_view(), name='relatorio_notas_credito'),
    path('relatorios/notas-debito/', rel.RelatorioNotasDebitoView.as_view(), name='relatorio_notas_debito'),
    # Financeiros
    path('relatorios/contas-receber/', rel.RelatorioContasAReceberView.as_view(), name='relatorio_contas_receber'),
    path('relatorios/clientes-devedores/', rel.RelatorioClientesDevedoresView.as_view(), name='relatorio_clientes_devedores'),
    path('relatorios/fluxo-caixa/', rel.RelatorioFluxoCaixaView.as_view(), name='relatorio_fluxo_caixa'),
    path('relatorios/demonstrativo-receitas/', rel.RelatorioDemonstrativoReceitasView.as_view(), name='relatorio_demonstrativo_receitas'),
    path('relatorios/balancete/', rel.RelatorioBalanceteFinanceiroView.as_view(), name='relatorio_balancete'),
    # Executivos
    path('relatorios/dashboard/', rel.RelatorioDashboardFinanceiroView.as_view(), name='relatorio_dashboard'),
    path('relatorios/dashboard/json/', rel.dashboard_financeiro_json, name='relatorio_dashboard_json'),
    path('relatorios/fluxo-caixa/json/', rel.fluxo_caixa_json, name='relatorio_fluxo_caixa_json'),
    path('relatorios/indicadores-cobranca/', rel.RelatorioIndicadoresCobrancaView.as_view(), name='relatorio_indicadores_cobranca'),
    path('relatorios/receita-cliente/', rel.RelatorioReceitaPorClienteView.as_view(), name='relatorio_receita_cliente'),
    path('relatorios/receita-localizacao/', rel.RelatorioReceitaPorLocalizacaoView.as_view(), name='relatorio_receita_localizacao'),
    path('relatorios/receita-despachante/', rel.RelatorioReceitaPorDespachanteView.as_view(), name='relatorio_receita_despachante'),

]
