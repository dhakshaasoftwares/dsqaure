from django import forms
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from apps.core.permissions import ACTIONS, MODULES

from .models import User


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label=_("password"), widget=forms.PasswordInput, required=False,
        help_text=_("Leave blank to keep the current password"),
    )
    groups = forms.ModelMultipleChoiceField(
        label=_("roles"), queryset=Group.objects.order_by("name"),
        widget=forms.CheckboxSelectMultiple, required=False,
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone", "email",
                  "preferred_language", "groups", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["password"].required = True
            self.fields["password"].help_text = ""

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password, self.instance)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("password"):
            user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            self.save_m2m()
        return user


class RoleForm(forms.ModelForm):
    """Role name plus a module × action grid of permission checkboxes."""

    class Meta:
        model = Group
        fields = ["name"]
        labels = {"name": _("role name")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = set()
        if self.instance.pk:
            current = {
                f"{p.content_type.app_label}.{p.codename}"
                for p in self.instance.permissions.select_related("content_type")
            }
        self.grid = []
        for index, (label, models) in enumerate(MODULES):
            row = {"label": label, "cells": []}
            for action, action_label in ACTIONS:
                name = f"perm_{index}_{action}"
                codes = [f"{app}.{action}_{model}" for app, model in models]
                self.fields[name] = forms.BooleanField(
                    required=False, label=action_label, initial=all(c in current for c in codes)
                )
                row["cells"].append(name)
            self.grid.append(row)

    def grid_rows(self):
        for row in self.grid:
            yield row["label"], [self[name] for name in row["cells"]]

    def save(self, commit=True):
        group = super().save(commit=True)
        wanted = []
        for index, (_label, models) in enumerate(MODULES):
            for action, _action_label in ACTIONS:
                if self.cleaned_data.get(f"perm_{index}_{action}"):
                    for app, model in models:
                        wanted.append((app, f"{action}_{model}"))
        perms = [
            p for p in Permission.objects.select_related("content_type")
            if (p.content_type.app_label, p.codename) in set(wanted)
        ]
        group.permissions.set(perms)
        return group
