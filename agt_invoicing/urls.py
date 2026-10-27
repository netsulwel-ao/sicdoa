from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.agt_stats, name='agt_stats'),
    path('pendentes/', views.agt_pendentes, name='agt_pendentes'),
    path('estado/<int:id>/', views.agt_estado, name='agt_estado'),
    path('callback/', views.agt_callback, name='agt_callback'),
]
