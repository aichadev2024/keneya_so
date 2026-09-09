from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Comptes et contrôle d'accès"

    def ready(self):
        from . import signals  # noqa: F401  (branche les récepteurs de signaux)
