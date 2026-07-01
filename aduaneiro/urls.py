from django.urls import path
from . import views

app_name = 'aduaneiro'

urlpatterns = [
    # Formulário DU (criar / editar)
    path('',                             views.du_view,           name='du'),
    path('<str:du_uuid>/editar/',        views.du_view,           name='du_editar'),

    # CRUD
    path('lista/',                       views.du_lista,          name='du_lista'),
    path('<str:du_uuid>/ver/',           views.du_detalhe,        name='du_detalhe'),
    path('guardar/',                     views.du_guardar,        name='du_guardar'),
    path('<str:du_uuid>/historico/',     views.du_historico,      name='du_historico'),
    path('<str:du_uuid>/apagar/',        views.du_apagar,         name='du_apagar'),
    path('<str:du_uuid>/status/',        views.du_alterar_status, name='du_alterar_status'),
    path('<str:du_uuid>/pdf/',           views.du_download_pdf,   name='du_pdf'),

    # Pauta Aduaneira
    path('pauta-aduaneira/',             views.pauta_aduaneira_view, name='pauta_aduaneira'),
    path('pauta-aduaneira/api/',         views.pauta_aduaneira_api,  name='pauta_aduaneira_api'),

    # APIs de clientes
    path('api/consultar-nif/',           views.consultar_nif_cliente, name='consultar_nif_cliente'),
    path('api/criar-cliente/',           views.criar_cliente_rapido,  name='criar_cliente_rapido'),
    path('api/pesquisar/',               views.du_pesquisar,          name='du_pesquisar'),

    # API de vinhetas (proxy ao portal CDOA)
    path('api/vinhetas/',                views.api_vinhetas,          name='api_vinhetas'),
]
