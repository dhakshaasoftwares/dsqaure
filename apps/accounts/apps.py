from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self):
        from django.contrib.auth.models import Group

        from apps.core.audit import track

        from . import security  # noqa: F401  (connects login signals)
        from .models import User

        track(User, Group)
