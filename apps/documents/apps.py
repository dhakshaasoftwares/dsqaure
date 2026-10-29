from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.documents"

    def ready(self):
        from apps.core.audit import track

        from .models import Agreement, Client, DocumentTemplate, Quotation, WorkItem

        track(Client, WorkItem, Quotation, Agreement, DocumentTemplate)
