from django.apps import AppConfig


class FinanceiroConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "financeiro"

    def ready(self):
        import financeiro.signals
