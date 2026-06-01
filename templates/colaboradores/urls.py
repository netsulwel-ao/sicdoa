from django.urls import path
from . import views

urlpatterns = [
    # Dashboard do Colaborador
    path('', views.dashboard_colaborador_view, name='dashboard_colaborador'),
    
    # Meus Dados
    path('perfil/', views.perfil_view, name='colaborador_perfil'),
    path('documentos/', views.documentos_view, name='colaborador_documentos'),
    
    # Controlo de Presença
    path('presenca/', views.presenca_view, name='colaborador_presenca'),
    
    # Processo Salarial
    path('salario/', views.salario_view, name='colaborador_salario'),
    path('historico-salarial/', views.historico_salarial_view, name='colaborador_historico_salarial'),
    
    # Férias e Ausências
    path('ferias/', views.ferias_view, name='colaborador_ferias'),
    
    # Busca
    path('buscar/', views.buscar_view, name='colaborador_buscar'),
]
