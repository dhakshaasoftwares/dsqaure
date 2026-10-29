from datetime import timedelta

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import CompanySettings

from .models import FailedLogin


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def is_locked(username):
    company = CompanySettings.load()
    since = timezone.now() - timedelta(minutes=company.login_lockout_minutes)
    recent = FailedLogin.objects.filter(username__iexact=username, at__gte=since).count()
    return recent >= company.login_max_attempts


@receiver(user_login_failed)
def record_failure(sender, credentials, request=None, **kwargs):
    username = (credentials or {}).get("username")
    if username:
        FailedLogin.objects.create(username=username[:150], ip_address=client_ip(request))


@receiver(user_logged_in)
def clear_failures(sender, request, user, **kwargs):
    FailedLogin.objects.filter(username__iexact=user.get_username()).delete()


class LockoutAuthenticationForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "locked": _("Too many wrong passwords. This account is locked for %(minutes)s minutes."),
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        if username and is_locked(username):
            raise forms.ValidationError(
                self.error_messages["locked"], code="locked",
                params={"minutes": CompanySettings.load().login_lockout_minutes},
            )
        return super().clean()
