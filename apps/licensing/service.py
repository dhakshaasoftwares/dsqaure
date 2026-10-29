"""
Works out what the installation is allowed to do today.

    unconfigured  vendor has not set up licensing (no public key) – no limits
    trial         no key yet, within the trial period – everything works
    valid         key OK
    expiring      key OK, ends within WARN_DAYS – owner sees a reminder
    grace         key ended, still within its grace days – works, red warning
    expired       past grace / trial over / key invalid – read-only
"""

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _

from .keys import ALL_MODULES, LicenceError, load_public_key, verify
from .models import Installation

WARN_DAYS = 30


@dataclass
class LicenceStatus:
    state: str
    message: str = ""
    licence: object = None
    days_left: int | None = None
    ends_on: object = None
    error: str = ""

    @property
    def read_only(self):
        return self.state == "expired"

    @property
    def show_banner(self):
        return self.state in ("trial", "expiring", "grace", "expired")

    @property
    def max_users(self):
        if self.licence and self.state != "unconfigured":
            return self.licence.max_users
        return getattr(settings, "LICENCE_TRIAL_USERS", None) if self.state == "trial" else None

    def module_allowed(self, key):
        if self.licence is None or self.state == "unconfigured":
            return True
        return key in self.licence.modules


def today_for(installation):
    """Today's date, but never earlier than a date this installation has already seen."""
    today = timezone.localdate()
    if installation.last_seen_on and installation.last_seen_on > today:
        return installation.last_seen_on
    if installation.last_seen_on != today:
        installation.last_seen_on = today
        Installation.objects.filter(pk=installation.pk).update(last_seen_on=today)
    return today


def check_key(key_text, installation):
    public_key = load_public_key()
    if public_key is None:
        raise LicenceError(_("Licensing is not set up in this installation."))
    licence = verify(key_text, public_key)
    if licence.install_id != installation.install_id:
        raise LicenceError(_("This key was issued for installation %(other)s, not %(this)s.")
                           % {"other": licence.install_id, "this": installation.install_id})
    return licence


def get_status(installation=None):
    if load_public_key() is None:
        return LicenceStatus("unconfigured")
    installation = installation or Installation.load()
    today = today_for(installation)

    if not installation.licence_key:
        trial_days = getattr(settings, "LICENCE_TRIAL_DAYS", 30)
        ends = installation.installed_on + timedelta(days=trial_days)
        left = (ends - today).days
        if left >= 0:
            return LicenceStatus("trial", _("Trial version: %(n)s days left. Enter a licence key to keep using it.")
                                 % {"n": left}, days_left=left, ends_on=ends)
        return LicenceStatus("expired", _("The trial has ended. The app is read-only until a licence key is entered."),
                             days_left=left, ends_on=ends)

    try:
        licence = check_key(installation.licence_key, installation)
    except LicenceError as exc:
        return LicenceStatus("expired", _("The licence key is not valid. The app is read-only."), error=str(exc))

    left = (licence.expires - today).days
    if left > WARN_DAYS:
        return LicenceStatus("valid", licence=licence, days_left=left, ends_on=licence.expires)
    if left >= 0:
        return LicenceStatus("expiring", _("Your licence ends on %(date)s (%(n)s days). Please renew.")
                             % {"date": licence.expires.strftime("%d %b %Y"), "n": left},
                             licence=licence, days_left=left, ends_on=licence.expires)
    grace_end = licence.expires + timedelta(days=licence.grace_days)
    if today <= grace_end:
        return LicenceStatus("grace", _("Your licence ended on %(date)s. Renew before %(grace)s or the app becomes read-only.")
                             % {"date": licence.expires.strftime("%d %b %Y"), "grace": grace_end.strftime("%d %b %Y")},
                             licence=licence, days_left=left, ends_on=licence.expires)
    return LicenceStatus("expired", _("Your licence ended on %(date)s. The app is read-only until it is renewed.")
                         % {"date": licence.expires.strftime("%d %b %Y")},
                         licence=licence, days_left=left, ends_on=licence.expires)


def active_user_count():
    from apps.accounts.models import User

    return User.objects.filter(is_active=True).count()


def all_modules():
    return list(ALL_MODULES)
