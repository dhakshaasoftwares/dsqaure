from django.apps import AppConfig


class ProgressConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.progress"

    def ready(self):
        from apps.core.audit import track

        from .models import ProgressUpdate, ProjectStage, StageTemplate

        track(StageTemplate, ProjectStage, ProgressUpdate)
