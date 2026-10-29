import secrets

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid reading mistakes


def new_install_id():
    raw = "".join(secrets.choice(ALPHABET) for _ in range(12))
    return f"DSQ-{raw[:4]}-{raw[4:8]}-{raw[8:]}"


class Installation(models.Model):
    """One row per installation: its identity and the licence key pasted in by the owner."""

    install_id = models.CharField(_("installation ID"), max_length=20, unique=True, default=new_install_id,
                                  editable=False)
    installed_on = models.DateField(_("installed on"), default=timezone.localdate, editable=False)
    licence_key = models.TextField(_("licence key"), blank=True)
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    # Highest date this installation has seen; stops "expiry" being dodged by turning the clock back.
    last_seen_on = models.DateField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = _("installation")

    def __str__(self):
        return self.install_id

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
