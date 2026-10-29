import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def new_token():
    return secrets.token_urlsafe(24)


class ShareLink(models.Model):
    """A secret, expiring web link to one document's PDF – for sending by WhatsApp / SMS."""

    token = models.CharField(max_length=64, unique=True, default=new_token, editable=False)
    doc_type = models.CharField(max_length=30)
    doc_id = models.PositiveIntegerField()
    label = models.CharField(_("document"), max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(_("expires"))
    revoked = models.BooleanField(_("stopped"), default=False)
    view_count = models.PositiveIntegerField(_("opened"), default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
        verbose_name = _("share link")
        verbose_name_plural = _("share links")

    def __str__(self):
        return self.label

    @property
    def is_active(self):
        return not self.revoked and self.expires_at > timezone.now()


class SentMessage(models.Model):
    """Log of documents sent to clients / suppliers."""

    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        WHATSAPP = "whatsapp", _("WhatsApp")
        LINK = "link", _("Link copied")

    doc_type = models.CharField(max_length=30)
    doc_id = models.PositiveIntegerField()
    channel = models.CharField(_("sent by"), max_length=10, choices=Channel.choices)
    recipient = models.CharField(_("to"), max_length=300)
    subject = models.CharField(_("subject"), max_length=200, blank=True)
    ok = models.BooleanField(default=True)
    error = models.CharField(max_length=300, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["doc_type", "doc_id"])]
        verbose_name = _("sent document")
        verbose_name_plural = _("sent documents")

    def __str__(self):
        return f"{self.get_channel_display()} → {self.recipient}"
