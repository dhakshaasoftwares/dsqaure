import threading
import zoneinfo

from django.http import Http404
from django.shortcuts import redirect
from django.utils import timezone

from .audit import set_current_user
from .models import CompanySettings

_local = threading.local()


def current_company():
    """Company settings for the current request (loaded once), or straight from the database."""
    company = getattr(_local, "company", None)
    return company if company is not None else CompanySettings.load()


# URL prefix → module switch in company settings
MODULE_PREFIXES = {
    "/attendance/": "attendance",
    "/payroll/": "payroll",
    "/inventory/": "inventory",
    "/progress/": "progress",
    "/documents/": "documents",
}


class CompanyMiddleware:
    """
    Loads the company configuration once per request, applies its time zone,
    blocks modules that are switched off, records the user for the audit
    log and sends a brand-new install to the setup wizard.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        company = CompanySettings.load()
        request.company = company
        _local.company = company
        try:
            timezone.activate(zoneinfo.ZoneInfo(company.timezone))
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            timezone.deactivate()

        path = request.path
        for prefix, module in MODULE_PREFIXES.items():
            if path.startswith(prefix) and not company.module_enabled(module):
                raise Http404("Module switched off")

        user = getattr(request, "user", None)
        if (user is not None and not user.is_authenticated and path.startswith("/accounts/login")
                and _needs_setup()):
            return redirect("core:setup")

        set_current_user(user)
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)
            _local.company = None


def _needs_setup():
    from apps.accounts.models import User

    return not User.objects.exists()
