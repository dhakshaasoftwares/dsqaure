"""
Automatic audit trail. Apps call ``track(Model)`` in their AppConfig.ready();
every create / change / delete of those models is written to AuditLog with
the logged-in user taken from the current request.
"""

import threading
from datetime import date, datetime
from decimal import Decimal

from django.db.models.fields.files import FieldFile
from django.db.models.signals import post_delete, post_save, pre_save

_state = threading.local()
EXCLUDED_FIELDS = {"password", "email_password", "licence_key", "last_login", "updated_at", "created_at"}


def set_current_user(user):
    _state.user = user


def get_current_user():
    user = getattr(_state, "user", None)
    return user if user is not None and user.is_authenticated else None


def _plain(value):
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or ""
    return value


def _snapshot(instance):
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in EXCLUDED_FIELDS:
            continue
        data[field.name] = _plain(getattr(instance, field.attname))
    return data


def _pre_save(sender, instance, **kwargs):
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).first()
        instance._audit_before = _snapshot(old) if old else None


def _write(instance, action, changes):
    from .models import AuditLog

    AuditLog.objects.create(
        user=get_current_user(),
        action=action,
        model=instance._meta.verbose_name[:100],
        object_id=str(instance.pk),
        object_repr=str(instance)[:200],
        changes=changes,
    )


def _post_save(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    after = _snapshot(instance)
    if created:
        _write(instance, "create", {})
        return
    before = getattr(instance, "_audit_before", None) or {}
    changes = {k: [before.get(k), v] for k, v in after.items() if before.get(k) != v}
    if changes:
        _write(instance, "update", changes)


def _post_delete(sender, instance, **kwargs):
    _write(instance, "delete", {})


def track(*models):
    for model in models:
        uid = f"audit-{model._meta.label}"
        pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "-pre")
        post_save.connect(_post_save, sender=model, dispatch_uid=uid + "-post")
        post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "-del")
