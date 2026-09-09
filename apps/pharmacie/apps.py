from django.apps import AppConfig


class PharmacieConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pharmacie"
    verbose_name = "Pharmacie"

    def ready(self):
        from . import signals  # noqa: F401
