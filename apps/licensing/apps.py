from django.apps import AppConfig


class LicensingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.licensing"

    def ready(self):
        from apps.core.audit import track

        from .models import Installation

        track(Installation)
