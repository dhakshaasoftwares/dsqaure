from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self):
        from .audit import track
        from .models import CompanySettings, NumberSequence, Project, Unit

        track(CompanySettings, NumberSequence, Project, Unit)
