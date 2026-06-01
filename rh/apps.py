from django.apps import AppConfig


class RhConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rh'

    def ready(self):
        import rh.signals
