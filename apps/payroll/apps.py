from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payroll"

    def ready(self):
        from apps.core.audit import track

        from .models import PayComponent, PayrollRun, SalaryAdvance

        track(PayComponent, PayrollRun, SalaryAdvance)
