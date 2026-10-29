from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """Login account. Roles are Django groups, managed from the Roles screen."""

    phone = models.CharField(_("phone"), max_length=20, blank=True)
    preferred_language = models.CharField(
        _("preferred language"),
        max_length=8,
        choices=[("en", "English"), ("ta", "தமிழ்")],
        default="en",
    )

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_names(self):
        if self.is_superuser:
            return [_("Owner")]
        return [g.name for g in self.groups.all()]


class FailedLogin(models.Model):
    """Wrong-password attempts, used to lock an account for a while after too many."""

    username = models.CharField(max_length=150, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-at"]
