from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render
from users import views as user_views
from users import views_session as session_views
from rh import views_public


def _error500(request):
    return render(request, '500.html', status=500)


def _error404(request, exception=None):
    return render(request, '404.html', status=404)


handler500 = _error500
handler404 = _error404

urlpatterns = [
    path('admin/', admin.site.urls),

    # Autenticação
    path('', user_views.login_view, name='login'),
    path('login/', user_views.login_view, name='login'),
    path('login-portal/', user_views.login_portal_view, name='login_portal'),
    path('logout/', user_views.logout_view, name='logout'),

    # Perfil do utilizador (despachante/admin/operador)
    path('perfil/', user_views.meu_perfil_view, name='meu_perfil'),
    path('perfil/guardar/', user_views.meu_perfil_guardar, name='meu_perfil_guardar'),
    path('perfil/senha/', user_views.meu_perfil_senha, name='meu_perfil_senha'),
    path('perfil/assinatura/', user_views.meu_perfil_assinatura, name='meu_perfil_assinatura'),
    path('perfil/foto/', user_views.meu_perfil_foto, name='meu_perfil_foto'),
    path('perfil/foto/remover/', user_views.meu_perfil_foto_remover, name='meu_perfil_foto_remover'),

    # Dashboard
    path('dashboard/', user_views.dashboard_view, name='dashboard'),
    path('dashboard-colaborador/', user_views.dashboard_colaborador_view, name='dashboard_colaborador'),
    
    # Páginas do Colaborador
    path('colaborador/perfil/', user_views.perfil_view, name='colaborador_perfil'),
    path('colaborador/documentos/', user_views.documentos_view, name='colaborador_documentos'),
    path('colaborador/presenca/', user_views.presenca_view, name='colaborador_presenca'),
    path('colaborador/processo-salarial/', user_views.processo_salarial_view, name='colaborador_processo_salarial'),
    path('colaborador/salario/', user_views.salario_view, name='colaborador_salario'),
    path('colaborador/historico-salarial/', user_views.historico_salarial_view, name='colaborador_historico_salarial'),
    path('colaborador/ferias/', user_views.ferias_view, name='colaborador_ferias'),
    path('colaborador/buscar/', user_views.buscar_view, name='colaborador_buscar'),
    
    # Teste de Email
    path('testar-email/', user_views.testar_email_view, name='testar_email'),

    # Gestão de Funções
    path('users/funcoes/', user_views.funcoes_lista_view, name='funcoes_lista'),
    path('users/funcoes/novo/', user_views.funcao_novo_view, name='funcao_novo'),
    path('users/funcoes/<int:pk>/editar/', user_views.funcao_editar_view, name='funcao_editar'),
    path('users/funcoes/<int:pk>/permissoes/', user_views.funcao_permissoes_view, name='funcao_permissoes'),
    path('users/funcoes/<int:pk>/eliminar/', user_views.funcao_eliminar_view, name='funcao_eliminar'),
    path('users/api/funcoes/permissoes/', user_views.api_funcao_permissoes, name='funcao_api_permissoes'),
    path('users/api/funcoes/<int:pk>/permissoes/', user_views.api_funcao_listar_permissoes, name='funcao_api_listar_permissoes'),

    # Logs de Atividade
    path('logs/', user_views.logs_atividade_view, name='logs_atividade'),

    # Manual do Utilizador
    path('manual/', user_views.manual_utilizador_view, name='manual_utilizador'),

    # Gestão de Sessão
    path('extend-session/', session_views.extend_session_view, name='extend_session'),
    path('session-status/', session_views.session_status_view, name='session_status'),
    path('users/api/renovar-sessao/', session_views.extend_session_view, name='renovar_sessao'),
    path('users/api/sessao-status/', session_views.session_status_view, name='sessao_status'),

    # Gestão Aduaneira
    path('du/', include('aduaneiro.urls')),

    # URLs Públicas ATS (não requerem autenticação)
    path('candidatar/<uuid:link_uuid>/', views_public.candidatura_externa_view, name='candidatura_externa'),
    path('vaga/<uuid:link_uuid>/', views_public.vaga_publica_view, name='vaga_publica'),

    # Recursos Humanos
    path('rh/', include('rh.urls')),

    # Governança / Assembleias
    path('governanca/', include('governanca.urls')),

    # Clientes
    path('clientes/', include('clientes.urls')),

    # Utilitários (reporte de erros, etc.)
    path('utils/', include('utils.error_urls')),

    # Financeiro
    path('financeiro/', include('financeiro.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
