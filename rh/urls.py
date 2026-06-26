from django.urls import path
from . import views
from . import views_public
from . import views_admin
from . import views_institucional

urlpatterns = [
    # ── Colaboradores Institucionais (Equipa do Administrador) ────────────
    path('admin/colaboradores-institucionais/',                                         views_admin.admin_colaboradores_inst_view,          name='rh_admin_colaboradores_inst'),
    path('admin/colaboradores-institucionais/<int:pk>/editar/',                         views_admin.admin_colaborador_inst_editar_view,     name='rh_admin_colaborador_inst_editar'),
    path('admin/colaboradores-institucionais/presencas/',                               views_admin.admin_presencas_inst_view,              name='rh_admin_presencas_inst'),
    path('admin/colaboradores-institucionais/presencas/registar/',                      views_admin.admin_presenca_inst_registar_view,      name='rh_admin_presenca_inst_registar'),
    path('admin/colaboradores-institucionais/presencas/<int:pk>/acao/',                 views_admin.admin_presenca_inst_aprovar_view,       name='rh_admin_presenca_inst_acao'),
    path('admin/colaboradores-institucionais/ferias/',                                  views_admin.admin_ferias_inst_view,                 name='rh_admin_ferias_inst'),
    path('admin/colaboradores-institucionais/ferias/<int:pk>/acao/',                    views_admin.admin_ferias_inst_acao_view,            name='rh_admin_ferias_inst_acao'),
    path('admin/colaboradores-institucionais/avaliacoes/',                              views_admin.admin_avaliacoes_inst_view,             name='rh_admin_avaliacoes_inst'),
    path('admin/colaboradores-institucionais/avaliacoes/ciclo/novo/',                   views_admin.admin_ciclo_inst_novo_view,             name='rh_admin_ciclo_inst_novo'),
    path('admin/colaboradores-institucionais/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/', views_admin.admin_avaliacao_inst_nova_view,         name='rh_admin_avaliacao_inst_nova'),
    path('admin/colaboradores-institucionais/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/', views_admin.admin_avaliacao_inst_nova_view, name='rh_admin_avaliacao_inst_editar'),
    path('admin/colaboradores-institucionais/salarios/',                                views_admin.admin_salarios_inst_view,               name='rh_admin_salarios_inst'),
    path('admin/colaboradores-institucionais/salarios/novo/',                           views_admin.admin_salario_inst_novo_view,           name='rh_admin_salario_inst_novo'),

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
    path('filiais/<int:pk>/dashboard/', views.filial_dashboard_view, name='rh_filial_dashboard'),
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
    path('colaboradores/<int:pk>/cargo/',           views.colaborador_cargo_view,          name='rh_colaborador_cargo'),
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
    path('recrutamento/<int:pk>/eliminar/',                 views.vaga_eliminar_view,        name='rh_vaga_eliminar'),
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

    # Cargos da Banca
    path('cargos/',                           views.cargos_lista_view,    name='rh_cargos_lista'),
    path('cargos/novo/',                      views.cargo_novo_view,     name='rh_cargo_novo'),
    path('cargos/<int:pk>/editar/',           views.cargo_editar_view,   name='rh_cargo_editar'),
    path('cargos/<int:pk>/eliminar/',         views.cargo_eliminar_view, name='rh_cargo_eliminar'),

    # Avaliações
    path('avaliacoes/',                                         views.avaliacoes_view,      name='rh_avaliacoes'),
    path('avaliacoes/ciclo/novo/',                              views.ciclo_novo_view,      name='rh_ciclo_novo'),
    path('avaliacoes/ciclo/<int:pk>/editar/',                   views.ciclo_editar_view,    name='rh_ciclo_editar'),
    path('avaliacoes/ciclo/<int:pk>/apagar/',                   views.ciclo_apagar_view,    name='rh_ciclo_apagar'),
    path('avaliacoes/ciclo/<int:pk>/',                          views.ciclo_detalhe_view,   name='rh_ciclo_detalhe'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/',            views.avaliacao_form_view,  name='rh_avaliacao_nova'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/', views.avaliacao_form_view, name='rh_avaliacao_editar'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/ver/', views.avaliacao_detalhe_view, name='rh_avaliacao_detalhe'),
    path('avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/apagar/', views.avaliacao_apagar_view, name='rh_avaliacao_apagar'),

    # ── RH Institucional ────────────────────────────────────────────────────
    # Dashboard
    path('institucional/',                                                  views_institucional.inst_dashboard_view,              name='rh_inst_dashboard'),

    # Subsídios
    path('institucional/subsidios/',                                        views_institucional.inst_subsidios_view,              name='rh_inst_subsidios'),
    path('institucional/subsidios/novo/',                                   views_institucional.inst_subsidio_novo_view,          name='rh_inst_subsidio_novo'),
    path('institucional/subsidios/<int:pk>/editar/',                        views_institucional.inst_subsidio_editar_view,        name='rh_inst_subsidio_editar'),
    path('institucional/subsidios/<int:pk>/apagar/',                        views_institucional.inst_subsidio_apagar_view,        name='rh_inst_subsidio_apagar'),

    # Processamento Salarial
    path('institucional/salarios/',                                         views_institucional.inst_salarios_view,               name='rh_inst_salarios'),
    path('institucional/salarios/novo/',                                    views_institucional.inst_salario_novo_view,           name='rh_inst_salario_novo'),
    path('institucional/salarios/<int:pk>/',                                views_institucional.inst_salario_detalhe_view,        name='rh_inst_salario_detalhe'),
    path('institucional/salarios/<int:pk>/apagar/',                         views_institucional.inst_salario_apagar_view,         name='rh_inst_salario_apagar'),
    path('institucional/salarios/<int:pk>/download/',                       views_institucional.inst_salario_download_view,       name='rh_inst_salario_download'),

    # Recrutamento — Vagas
    path('institucional/recrutamento/',                                     views_institucional.inst_vagas_view,                  name='rh_inst_vagas'),
    path('institucional/recrutamento/nova/',                                views_institucional.inst_vaga_nova_view,              name='rh_inst_vaga_nova'),
    path('institucional/recrutamento/<int:pk>/editar/',                     views_institucional.inst_vaga_editar_view,            name='rh_inst_vaga_editar'),
    path('institucional/recrutamento/<int:pk>/eliminar/',                   views_institucional.inst_vaga_eliminar_view,          name='rh_inst_vaga_eliminar'),

    # Recrutamento — Candidaturas
    path('institucional/recrutamento/<int:vaga_pk>/candidaturas/',          views_institucional.inst_candidaturas_view,           name='rh_inst_candidaturas'),
    path('institucional/recrutamento/candidatura/<int:pk>/',                views_institucional.inst_candidatura_detalhe_view,    name='rh_inst_candidatura_detalhe'),
    path('institucional/recrutamento/candidatura/<int:pk>/estado/',         views_institucional.inst_candidatura_estado_view,     name='rh_inst_candidatura_estado'),

    # Recrutamento — Entrevistas
    path('institucional/recrutamento/candidatura/<int:candidatura_pk>/entrevista/nova/', views_institucional.inst_entrevista_nova_view,     name='rh_inst_entrevista_nova'),
    path('institucional/recrutamento/entrevista/<int:pk>/resultado/',                     views_institucional.inst_entrevista_resultado_view, name='rh_inst_entrevista_resultado'),

    # Recrutamento — Integração
    path('institucional/recrutamento/candidatura/<int:candidatura_pk>/integracao/nova/',  views_institucional.inst_integracao_nova_view,    name='rh_inst_integracao_nova'),
    path('institucional/recrutamento/integracao/<int:pk>/',                               views_institucional.inst_integracao_detalhe_view, name='rh_inst_integracao_detalhe'),

    # Recrutamento — Público
    path('recrutamento/vaga/<uuid:link_uuid>/',                           views_institucional.inst_vaga_publica_view,          name='rh_inst_vaga_publica'),
    path('recrutamento/vaga/<uuid:link_uuid>/candidatar/',                views_institucional.inst_candidatura_externa_view,   name='rh_inst_candidatura_publica'),

    # Presenças
    path('institucional/presencas/',                                       views_institucional.inst_presencas_view,             name='rh_inst_presencas'),
    path('institucional/presencas/registar/',                              views_institucional.inst_presenca_registar_view,     name='rh_inst_presenca_registar'),
    path('institucional/presencas/<int:pk>/aprovar/',                      views_institucional.inst_presenca_aprovar_view,      name='rh_inst_presenca_aprovar'),
    path('institucional/presencas/<int:pk>/apagar/',                       views_institucional.inst_presenca_apagar_view,       name='rh_inst_presenca_apagar'),

    # Férias
    path('institucional/ferias/',                                          views_institucional.inst_ferias_pedir_view,          name='rh_inst_ferias'),
    path('institucional/ferias/pedir/',                                    views_institucional.inst_ferias_pedir_view,          name='rh_inst_ferias_pedir'),
    path('institucional/ferias/<int:pk>/aprovar/',                         views_institucional.inst_ferias_aprovar_view,        name='rh_inst_ferias_aprovar'),
    path('institucional/ferias/<int:pk>/apagar/',                          views_institucional.inst_ferias_apagar_view,         name='rh_inst_ferias_apagar'),

    # Avaliações
    path('institucional/avaliacoes/',                                      views_institucional.inst_avaliacoes_view,            name='rh_inst_avaliacoes'),
    path('institucional/avaliacoes/ciclo/novo/',                           views_institucional.inst_ciclo_novo_view,            name='rh_inst_ciclo_novo'),
    path('institucional/avaliacoes/ciclo/<int:pk>/',                       views_institucional.inst_ciclo_detalhe_view,         name='rh_inst_ciclo_detalhe'),
    path('institucional/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/',         views_institucional.inst_avaliacao_form_view,        name='rh_inst_avaliacao_nova'),
    path('institucional/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/', views_institucional.inst_avaliacao_form_view,    name='rh_inst_avaliacao_editar'),
    path('institucional/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/ver/', views_institucional.inst_avaliacao_detalhe_view,   name='rh_inst_avaliacao_detalhe'),
    path('institucional/avaliacoes/ciclo/<int:ciclo_pk>/avaliar/<int:col_pk>/apagar/', views_institucional.inst_avaliacao_apagar_view, name='rh_inst_avaliacao_apagar'),

    ]
