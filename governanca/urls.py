from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='governanca_index'),

    # Assembleias
    path('assembleias/', views.lista_assembleias, name='governanca_assembleias'),
    path('assembleia/nova/', views.nova_assembleia, name='governanca_nova_assembleia'),
    path('assembleia/<int:pk>/', views.detalhe_assembleia, name='governanca_detalhe'),
    path('assembleia/<int:pk>/editar/', views.editar_assembleia, name='governanca_editar'),

    # Sala da Assembleia (ao vivo)
    path('assembleia/<int:pk>/sala/', views.sala_assembleia, name='governanca_sala'),

    # Gestão da Assembleia (admin/mesa)
    path('assembleia/<int:pk>/gerir/', views.gerir_assembleia, name='governanca_gerir'),

    # API: Presença
    path('api/assembleia/<int:pk>/registar-presenca/', views.api_registar_presenca, name='governanca_api_presenca'),
    path('api/assembleia/<int:pk>/presencas/', views.api_listar_presencas, name='governanca_api_presencas'),

    # API: Procuração
    path('api/assembleia/<int:pk>/solicitar-procuracao/', views.api_solicitar_procuracao, name='governanca_api_solicitar_procuracao'),
    path('api/assembleia/<int:pk>/confirmar-procuracao/', views.api_confirmar_procuracao, name='governanca_api_confirmar_procuracao'),
    path('api/assembleia/<int:pk>/minhas-procuracao/', views.api_minhas_procuracao, name='governanca_api_minhas_procuracao'),
    path('api/assembleia/<int:pk>/cancelar-procuracao/', views.api_cancelar_procuracao, name='governanca_api_cancelar_procuracao'),

    # API: Pauta - Reabertura
    path('api/pauta/<int:pk>/reabrir-votacao/', views.api_reabrir_votacao, name='governanca_api_reabrir_votacao'),

    # API: Votação
    path('api/pauta/<int:pk>/iniciar-votacao/', views.api_iniciar_votacao, name='governanca_api_iniciar_votacao'),
    path('api/pauta/<int:pk>/encerrar-votacao/', views.api_encerrar_votacao, name='governanca_api_encerrar_votacao'),
    path('api/pauta/<int:pk>/votar/', views.api_votar, name='governanca_api_votar'),
    path('api/pauta/<int:pk>/resultados/', views.api_resultados_pauta, name='governanca_api_resultados_pauta'),
    path('api/pauta/<int:pk>/votos/', views.api_votos_pauta, name='governanca_api_votos_pauta'),
    path('api/pauta/<int:pk>/verificar/', views.api_verificar_voto, name='governanca_api_verificar_voto'),

    # API: Assembleia
    path('api/assembleia/<int:pk>/status/', views.api_status_assembleia, name='governanca_api_status'),
    path('api/assembleia/<int:pk>/iniciar/', views.api_iniciar_assembleia, name='governanca_api_iniciar'),
    path('api/assembleia/<int:pk>/concluir/', views.api_concluir_assembleia, name='governanca_api_concluir'),
    path('api/assembleia/<int:pk>/cancelar/', views.api_cancelar_assembleia, name='governanca_api_cancelar'),

    # API: Manifesto / Ata
    path('api/assembleia/<int:pk>/gerar-manifesto/', views.api_gerar_manifesto, name='governanca_api_manifesto'),
    path('api/assembleia/<int:pk>/publicar-ata/', views.api_publicar_ata, name='governanca_api_publicar_ata'),
    path('api/ata/<int:pk>/assinar/', views.api_assinar_ata, name='governanca_api_assinar_ata'),

    # LiveKit Token & Control
    path('api/livekit/token/', views.api_livekit_token, name='governanca_api_livekit_token'),
    path('api/livekit/refresh-token/', views.api_livekit_refresh_token, name='governanca_api_livekit_refresh'),
    path('api/livekit/mute/', views.api_livekit_mute, name='governanca_api_livekit_mute'),
    path('api/livekit/participants/', views.api_livekit_participants, name='governanca_api_livekit_participants'),

    # API: Recording
    path('api/recording/start/', views.api_recording_start, name='governanca_api_recording_start'),
    path('api/recording/stop/', views.api_recording_stop, name='governanca_api_recording_stop'),

    # API: Sala (dados auxiliares)
    path('api/assembleia/<int:pk>/dados/', views.api_assembleia_dados, name='governanca_api_assembleia_dados'),
    path('api/assembleia/<int:pk>/mesa/listar/', views.api_mesa_listar, name='governanca_api_mesa_listar'),
    path('api/assembleia/<int:pk>/presencas/listar/', views.api_presencas_listar, name='governanca_api_presencas_listar'),

    # Notificações
    path('notificacoes/', views.pagina_notificacoes, name='governanca_notificacoes'),
    path('api/notificacoes/', views.api_notificacoes, name='governanca_api_notificacoes'),
    path('api/notificacoes/marcar-lida/<int:pk>/', views.api_notificacao_marcar_lida, name='governanca_api_notificacao_lida'),
    path('api/notificacoes/marcar-todas/', views.api_notificacoes_marcar_todas_lidas, name='governanca_api_notificacoes_marcar_todas'),

    # Repositório de Atas
    path('atas/', views.repositorio_atas, name='governanca_atas'),

    # API: Mesa da Assembleia
    path('api/assembleia/<int:pk>/mesa/adicionar/', views.api_mesa_adicionar, name='governanca_api_mesa_adicionar'),
    path('api/assembleia/<int:pk>/mesa/remover/<int:membro_pk>/', views.api_mesa_remover, name='governanca_api_mesa_remover'),

    # API: Chat
    path('api/assembleia/<int:pk>/chat/', views.api_chat_historico, name='governanca_api_chat'),

    # API: Documentos
    path('api/assembleia/<int:pk>/documentos/upload/', views.api_upload_documento, name='governanca_api_upload_documento'),
    path('api/assembleia/<int:pk>/documentos/listar/', views.api_listar_documentos, name='governanca_api_listar_documentos'),
    path('api/assembleia/<int:pk>/documentos/<int:doc_pk>/publicar/', views.api_publicar_documento, name='governanca_api_publicar_documento'),
    path('api/assembleia/<int:pk>/documentos/<int:doc_pk>/remover/', views.api_remover_documento, name='governanca_api_remover_documento'),

    # ═══════════════════════════════════════════════════════════════════════════
    # Submódulo 3: Escuta Activa, Fórum & Transparência
    # ═══════════════════════════════════════════════════════════════════════════

    # Páginas HTML
    path('consultas/', views.consulta_lista, name='governanca_consultas'),
    path('consulta/nova/', views.consulta_criar, name='governanca_consulta_criar'),
    path('consulta/<int:pk>/', views.consulta_detalhe, name='governanca_consulta_detalhe'),
    path('consulta/<int:pk>/editar/', views.consulta_editar, name='governanca_consulta_editar'),
    path('consulta/<int:pk>/relatorio/', views.consulta_relatorio, name='governanca_consulta_relatorio'),

    # API
    path('api/consulta/<int:pk>/publicar/', views.api_consulta_publicar, name='governanca_api_consulta_publicar'),
    path('api/consulta/<int:pk>/comentar/', views.api_consulta_comentar, name='governanca_api_consulta_comentar'),
    path('api/consulta/<int:pk>/responder/', views.api_consulta_responder, name='governanca_api_consulta_responder'),
    path('api/consulta/<int:pk>/abrir-votacao/', views.api_consulta_abrir_votacao, name='governanca_api_consulta_abrir_votacao'),
    path('api/consulta/<int:pk>/votar/', views.api_consulta_votar, name='governanca_api_consulta_votar'),
    path('api/consulta/<int:pk>/encerrar/', views.api_consulta_encerrar, name='governanca_api_consulta_encerrar'),
    path('api/consulta/<int:pk>/relatorio/', views.api_consulta_gerar_relatorio, name='governanca_api_consulta_gerar_relatorio'),
    path('api/consulta/<int:pk>/versao-final/', views.api_consulta_publicar_versao_final, name='governanca_api_consulta_versao_final'),
    path('api/consulta/<int:pk>/rejeitar/', views.api_consulta_rejeitar, name='governanca_api_consulta_rejeitar'),

    # ═══════════════════════════════════════════════════════════════════════════
    # Gestão Financeira de Quotas
    # ═══════════════════════════════════════════════════════════════════════════

    # Páginas HTML
    path('quotas/', views.quotas_dashboard, name='governanca_quotas_dashboard'),
    path('quotas/faturas/', views.quotas_faturas, name='governanca_quotas_faturas'),
    path('quotas/fatura/<uuid:fatura_uuid>/', views.quotas_fatura_detalhe, name='governanca_quota_detalhe'),
    path('quotas/certidao/', views.quotas_certidao, name='governanca_quotas_certidao'),
    path('quotas/carteira/', views.quotas_carteira, name='governanca_quotas_carteira'),

    # Admin
    path('quotas/admin/', views.quotas_admin_dashboard, name='governanca_quotas_admin'),
    path('quotas/admin/pagamentos/', views.quotas_admin_pagamentos, name='governanca_quotas_admin_pagamentos'),
    path('quotas/admin/config/', views.quotas_admin_config, name='governanca_quotas_admin_config'),
    path('quotas/admin/relatorios/', views.quotas_admin_relatorios, name='governanca_quotas_admin_relatorios'),
    path('quotas/admin/gerar-retroativo/', views.quotas_admin_gerar_retroativo, name='governanca_quotas_admin_gerar_retroativo'),

    # API: Pagamentos
    path('quotas/api/pagar/<uuid:fatura_uuid>/', views.api_quotas_pagar, name='governanca_api_quotas_pagar'),
    path('quotas/api/marcar-paga/<uuid:fatura_uuid>/', views.api_quotas_marcar_paga, name='governanca_api_quotas_marcar_paga'),
    path('quotas/api/pagamento/<int:pk>/confirmar/', views.api_quotas_confirmar_pagamento, name='governanca_api_quotas_confirmar'),

    # API: Certidão
    path('quotas/api/emitir-certidao/', views.api_quotas_emitir_certidao, name='governanca_api_quotas_emitir_certidao'),

    # API: Estado / Listagem
    path('quotas/api/estado/', views.api_quotas_verificar_estado, name='governanca_api_quotas_estado'),
    path('quotas/api/listar/', views.api_quotas_listar, name='governanca_api_quotas_listar'),
    path('quotas/api/dashboard/', views.api_quotas_dashboard, name='governanca_api_quotas_dashboard'),

    # API: Config
    path('quotas/api/salvar-config/', views.api_quotas_salvar_config, name='governanca_api_quotas_salvar_config'),

    # API: Carteira
    path('quotas/api/renovar-carteira/', views.api_quotas_renovar_carteira, name='governanca_api_quotas_renovar_carteira'),
    path('quotas/api/carteira/', views.api_quotas_carteira, name='governanca_api_quotas_carteira'),

    # API: Estado (admin)
    path('quotas/api/definir-estado/<int:pk>/', views.api_quotas_definir_estado, name='governanca_api_quotas_definir_estado'),

    # API: Buscar membros (admin)
    path('quotas/api/buscar-membros/', views.api_quotas_buscar_membros, name='governanca_api_quotas_buscar_membros'),

    # API: Geração retroativa (admin)
    path('quotas/api/gerar-retroativo/', views.api_quotas_gerar_retroativo, name='governanca_api_quotas_gerar_retroativo'),

    # API: Cancelar quota (admin)
    path('quotas/api/cancelar/<uuid:fatura_uuid>/', views.api_quotas_cancelar, name='governanca_api_quotas_cancelar'),

    # API: Isenções (admin)
    path('quotas/api/isencoes/', views.api_quotas_listar_isencoes, name='governanca_api_quotas_listar_isencoes'),
    path('quotas/api/isencoes/criar/', views.api_quotas_criar_isencao, name='governanca_api_quotas_criar_isencao'),

    # API: Histórico
    path('quotas/api/historico/<uuid:fatura_uuid>/', views.api_quotas_historico, name='governanca_api_quotas_historico'),

    # API: Verificar vencimentos (manual trigger)
    path('quotas/api/verificar-vencimentos/', views.api_quotas_verificar_vencimentos, name='governanca_api_quotas_verificar_vencimentos'),

    # ═══════════════════════════════════════════════════════════════════════════
    # Submódulo 1 — Componentes Adicionais
    # ═══════════════════════════════════════════════════════════════════════════

    # Convocatórias
    path('assembleia/<int:pk>/convocatorias/', views.lista_convocatorias, name='governanca_convocatorias'),
    path('assembleia/<int:pk>/convocatoria/nova/', views.criar_convocatoria, name='governanca_criar_convocatoria'),
    path('api/convocatoria/<int:pk>/publicar/', views.api_convocatoria_publicar, name='governanca_api_convocatoria_publicar'),
    path('api/convocatoria/<int:pk>/confirmar-rececao/', views.api_convocatoria_confirmar_rececao, name='governanca_api_convocatoria_confirmar'),

    # RSVP
    path('api/assembleia/<int:pk>/responder-presenca/', views.api_responder_presenca, name='governanca_api_responder_presenca'),

    # Exportação
    path('assembleia/<int:pk>/exportar/pdf/', views.exportar_resultados_pdf, name='governanca_exportar_pdf'),
    path('assembleia/<int:pk>/exportar/excel/', views.exportar_resultados_excel, name='governanca_exportar_excel'),
    path('assembleia/<int:pk>/exportar/csv/', views.exportar_resultados_csv, name='governanca_exportar_csv'),

    # Logs
    path('assembleia/<int:pk>/logs/', views.assembleia_logs, name='governanca_logs'),

    # Secretário - Gestão de Documentos
    path('secretario/', views.secretario_documentos, name='governanca_secretario_documentos'),
    path('api/secretario/assembleias/', views.api_secretario_assembleias, name='governanca_api_secretario_assembleias'),

    # Utilizadores (Admin)
    path('utilizadores/', views.gerir_utilizadores, name='governanca_gerir_utilizadores'),
    path('utilizadores/novo/', views.utilizador_novo_view, name='governanca_utilizador_novo'),
    path('utilizadores/<int:usuario_id>/editar/', views.utilizador_editar_view, name='governanca_utilizador_editar'),
    path('utilizadores/<int:usuario_id>/permissoes/', views.utilizador_permissoes_view, name='governanca_utilizador_permissoes'),
    path('api/utilizadores/criar/', views.api_utilizador_criar, name='governanca_api_utilizador_criar'),
    path('api/utilizadores/toggle-status/', views.api_utilizador_toggle_status, name='governanca_api_utilizador_toggle'),
    path('api/utilizadores/enviar-credenciais/', views.api_utilizador_enviar_credenciais, name='governanca_api_utilizador_credenciais'),
    path('api/utilizadores/permissoes/', views.api_utilizador_permissoes, name='governanca_api_utilizador_permissoes'),
    path('api/permissoes-usuario/', views.api_permissoes_usuario, name='governanca_api_permissoes_usuario'),
    path('api/utilizadores/atribuir-funcao/', views.api_utilizador_atribuir_funcao, name='governanca_api_utilizador_atribuir_funcao'),
    path('api/utilizadores/eliminar/', views.api_utilizador_eliminar, name='governanca_api_utilizador_eliminar'),

    # API: Gerar documentos (atas, relatórios, decretos)
    path('api/gerar-documento/', views.api_gerar_documento, name='governanca_api_gerar_documento'),

    # Visualizar documento gerado
    path('documento/<int:pk>/visualizar/', views.visualizar_documento, name='governanca_visualizar_documento'),
]
