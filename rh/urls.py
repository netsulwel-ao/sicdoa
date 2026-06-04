from django.urls import path
from . import views
from . import views_public
from . import views_admin

urlpatterns = [
    # ── Administração do Sistema (apenas Administradores) ──────────────────
    path('admin/despachantes/',                                     views_admin.admin_despachantes_view,                    name='admin_despachantes'),
    path('admin/despachantes/novo/',                                views_admin.admin_despachante_novo_view,                name='admin_despachante_novo'),
    path('admin/despachantes/<int:usuario_id>/',                    views_admin.admin_despachante_detalhe_view,             name='admin_despachante_detalhe'),
    path('admin/despachantes/<int:usuario_id>/editar/',             views_admin.admin_despachante_editar_view,              name='admin_despachante_editar'),
    path('admin/despachantes/<int:usuario_id>/toggle/',             views_admin.admin_despachante_toggle_view,              name='admin_despachante_toggle'),
    path('admin/despachantes/<int:usuario_id>/enviar-credenciais/', views_admin.admin_despachante_enviar_credenciais_view,  name='admin_despachante_enviar_credenciais'),
    path('admin/despachantes/<int:usuario_id>/cargo/',                 views_admin.admin_atribuir_cargo_view,                 name='admin_atribuir_cargo'),
    path('admin/bancas/',                                           views_admin.admin_bancas_view,                          name='admin_bancas'),
    path('admin/bancas/<int:banca_id>/',                            views_admin.admin_banca_detalhe_view,                   name='admin_banca_detalhe'),
    path('admin/bancas/<int:banca_id>/toggle/',                     views_admin.admin_banca_toggle_view,                    name='admin_banca_toggle'),

    # Banca
    path('banca/', views.banca_view, name='rh_banca'),
    path('banca/criar/', views.banca_criar_view, name='rh_banca_criar'),
    path('banca/editar/', views.banca_editar_view, name='rh_banca_editar'),

    # Filiais
    path('filiais/nova/', views.filial_nova_view, name='rh_filial_nova'),
    path('filiais/<int:pk>/', views.filial_detalhe_view, name='rh_filial_detalhe'),
    path('filiais/<int:pk>/editar/', views.filial_editar_view, name='rh_filial_editar'),
    path('filiais/responsavel/novo/temp/', views.filial_responsavel_novo_temp_view, name='rh_filial_responsavel_novo_temp'),
    path('filiais/<int:pk>/responsavel/novo/', views.filial_responsavel_novo_view, name='rh_filial_responsavel_novo'),
    path('filiais/<int:pk>/apagar/', views.filial_apagar_view, name='rh_filial_apagar'),

    # Colaboradores
    path('colaboradores/',                          views.colaboradores_view,       name='rh_colaboradores'),
    path('colaboradores/novo/',                     views.colaborador_novo_view,    name='rh_colaborador_novo'),
    path('colaboradores/<int:pk>/editar/',          views.colaborador_editar_view,  name='rh_colaborador_editar'),
    path('colaboradores/<int:pk>/dados/',           views.colaborador_dados_api,    name='rh_colaborador_dados'),
    path('colaboradores/<int:pk>/apagar/',          views.colaborador_apagar_view,  name='rh_colaborador_apagar'),
    path('colaboradores/<int:pk>/reenviar-email/',  views.colaborador_reenviar_email_view, name='rh_colaborador_reenviar_email'),
    path('documentos/<int:pk>/download/',           views.documento_colaborador_download, name='rh_documento_download'),
    path('documentos/<int:pk>/apagar/',             views.documento_colaborador_apagar_view, name='rh_documento_apagar'),

    # Processamento Salarial
    path('salarios/',               views.salarios_view,        name='rh_salarios'),
    path('salarios/novo/',          views.salario_novo_view,    name='rh_salario_novo'),
    path('salarios/<int:pk>/',      views.salario_detalhe_view, name='rh_salario_detalhe'),
    path('salarios/<int:pk>/apagar/', views.salario_apagar_view, name='rh_salario_apagar'),
    path('salarios/<int:pk>/download/', views.salario_download_view, name='rh_salario_download'),

    # Subsídios
    path('subsidios/',              views.subsidios_view,       name='rh_subsidios'),
    path('subsidios/novo/',         views.subsidio_novo_view,    name='rh_subsidio_novo'),
    path('subsidios/<int:pk>/editar/', views.subsidio_editar_view, name='rh_subsidio_editar'),
    path('subsidios/<int:pk>/apagar/', views.subsidio_apagar_view, name='rh_subsidio_apagar'),

    # Recrutamento — Vagas
    path('recrutamento/',                                   views.vagas_view,               name='rh_vagas'),
    path('recrutamento/nova/',                              views.vaga_nova_view,            name='rh_vaga_nova'),
    path('recrutamento/<int:pk>/editar/',                   views.vaga_editar_view,          name='rh_vaga_editar'),
    # Candidaturas
    path('recrutamento/<int:vaga_pk>/candidaturas/',        views.candidaturas_view,         name='rh_candidaturas'),
    path('recrutamento/candidatura/<int:pk>/',              views.candidatura_detalhe_view,  name='rh_candidatura_detalhe'),
    path('recrutamento/candidatura/<int:pk>/estado/',       views.candidatura_estado_view,   name='rh_candidatura_estado'),
    # Entrevistas
    path('recrutamento/candidatura/<int:candidatura_pk>/entrevista/nova/', views.entrevista_nova_view,     name='rh_entrevista_nova'),
    path('recrutamento/entrevista/<int:pk>/resultado/',                    views.entrevista_resultado_view, name='rh_entrevista_resultado'),
    # Integração
    path('recrutamento/candidatura/<int:candidatura_pk>/integracao/nova/', views.integracao_nova_view,    name='rh_integracao_nova'),
    path('recrutamento/integracao/<int:pk>/',                              views.integracao_detalhe_view, name='rh_integracao_detalhe'),

    # Presenças
    path('presencas/',                      views.presencas_view,           name='rh_presencas'),
    path('presencas/registar/',             views.presenca_registar_view,   name='rh_presenca_registar'),
    path('presencas/<int:pk>/aprovar/',     views.presenca_aprovar_view,    name='rh_presenca_aprovar'),
    path('presencas/<int:pk>/apagar/',      views.presenca_apagar_view,     name='rh_presenca_apagar'),

    # Férias
    path('ferias/',                         views.ferias_lista_view,        name='rh_ferias'),
    path('ferias/pedir/',                   views.ferias_pedir_view,        name='rh_ferias_pedir'),
    path('ferias/<int:pk>/aprovar/',        views.ferias_aprovar_view,      name='rh_ferias_aprovar'),
    path('ferias/<int:pk>/apagar/',         views.ferias_apagar_view,       name='rh_ferias_apagar'),

    # Avaliações
    path('avaliacoes/',                                         views.avaliacoes_view,      name='rh_avaliacoes'),
    path('avaliacoes/ciclo/novo/',                              views.ciclo_novo_view,      name='rh_ciclo_novo'),
    path('avaliacoes/ciclo/<int:pk>/',                          views.ciclo_detalhe_view,   name='rh_ciclo_detalhe'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/',            views.avaliacao_form_view,  name='rh_avaliacao_nova'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/', views.avaliacao_form_view, name='rh_avaliacao_editar'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/ver/', views.avaliacao_detalhe_view, name='rh_avaliacao_detalhe'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/apagar/', views.avaliacao_apagar_view, name='rh_avaliacao_apagar'),

    ]
