from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.permissions import PermRequired

from .forms import RoleForm, UserForm
from .models import User


class UserList(PermRequired, ListView):
    permission_required = "accounts.view_user"
    model = User
    template_name = "accounts/user_list.html"
    queryset = User.objects.prefetch_related("groups").order_by("username")


class UserCreate(PermRequired, CreateView):
    permission_required = "accounts.add_user"
    model = User
    form_class = UserForm
    template_name = "form.html"
    success_url = reverse_lazy("accounts:user_list")
    extra_context = {"title": _("New user")}


class UserUpdate(PermRequired, UpdateView):
    permission_required = "accounts.change_user"
    model = User
    form_class = UserForm
    template_name = "form.html"
    success_url = reverse_lazy("accounts:user_list")
    extra_context = {"title": _("Edit user")}

    def get_queryset(self):
        # Only the owner (superuser) can edit another owner account.
        qs = super().get_queryset()
        return qs if self.request.user.is_superuser else qs.filter(is_superuser=False)


class RoleList(PermRequired, ListView):
    permission_required = "auth.view_group"
    model = Group
    template_name = "accounts/role_list.html"
    queryset = Group.objects.prefetch_related("user_set").order_by("name")


class RoleCreate(PermRequired, CreateView):
    permission_required = "auth.add_group"
    model = Group
    form_class = RoleForm
    template_name = "accounts/role_form.html"
    success_url = reverse_lazy("accounts:role_list")
    extra_context = {"title": _("New role")}


class RoleUpdate(PermRequired, UpdateView):
    permission_required = "auth.change_group"
    model = Group
    form_class = RoleForm
    template_name = "accounts/role_form.html"
    success_url = reverse_lazy("accounts:role_list")
    extra_context = {"title": _("Edit role")}


class SetLanguage(LoginRequiredMixin, View):
    def post(self, request):
        lang = request.POST.get("language", "en")
        if lang in dict(User._meta.get_field("preferred_language").choices):
            request.user.preferred_language = lang
            request.user.save(update_fields=["preferred_language"])
            translation.activate(lang)
            messages.success(request, _("Language updated"))
        return redirect(request.POST.get("next") or "core:dashboard")
