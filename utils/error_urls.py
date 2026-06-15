from django.urls import path
from . import error_views

urlpatterns = [
    path('reportar-erro/', error_views.report_error_view, name='reportar_erro'),
]
