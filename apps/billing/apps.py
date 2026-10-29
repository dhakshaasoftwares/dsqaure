from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"

    def ready(self):
        from apps.core.audit import track

        from .models import ClientPayment, Invoice

        track(Invoice, ClientPayment)
