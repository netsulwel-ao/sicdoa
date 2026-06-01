from django.apps import AppConfig


class AduaneiroConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'aduaneiro'

    def ready(self):
        import aduaneiro.signals
