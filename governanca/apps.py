from django.apps import AppConfig

class GovernancaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'governanca'
    verbose_name = 'CDOA Governança Digital'

    def ready(self):
        import governanca.signals
