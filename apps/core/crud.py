"""
Small helper that produces list / add / edit / delete screens for simple
master data (suppliers, materials, units, templates …) so every
configuration screen looks and behaves the same.

    suppliers = Crud(Supplier, "supplier", fields=[...], columns=[...], search=["name"])
    urlpatterns += suppliers.urls()
"""

from django import forms
from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.translation import gettext as _
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .permissions import PermRequired


class Crud:
    def __init__(self, model, name, fields, columns, search=(), form_class=None, ordering=None,
                 paginate_by=50, intro="", widgets=None, filters=()):
        self.model = model
        self.name = name
        self.fields = fields
        self.columns = columns
        self.search = search
        self.ordering = ordering
        self.paginate_by = paginate_by
        self.intro = intro
        self.filters = filters
        meta = model._meta
        self.app_label = meta.app_label
        self.perm = lambda action: f"{meta.app_label}.{action}_{meta.model_name}"
        self.form_class = form_class or forms.modelform_factory(model, fields=fields, widgets=widgets or {})

    def url_name(self, action):
        return f"{self.name}_{action}"

    def column_headers(self):
        headers = []
        for col in self.columns:
            try:
                headers.append(self.model._meta.get_field(col).verbose_name)
            except Exception:  # property
                headers.append(col.replace("_", " "))
        return headers

    @staticmethod
    def cell(obj, col):
        display = getattr(obj, f"get_{col}_display", None)
        value = display() if display else getattr(obj, col)
        if callable(value):
            value = value()
        if value is True:
            return "✓"
        if value is False:
            return "—"
        return "" if value is None else value

    def views(self):
        crud = self

        class Base(PermRequired):
            model = crud.model

            def get_context_data(self, **kwargs):
                ctx = super().get_context_data(**kwargs)
                ns = self.request.resolver_match.namespace
                ctx.update({
                    "crud": crud,
                    "verbose_name": crud.model._meta.verbose_name,
                    "verbose_name_plural": crud.model._meta.verbose_name_plural,
                    "list_url": reverse(f"{ns}:{crud.url_name('list')}"),
                    "create_url": reverse(f"{ns}:{crud.url_name('create')}"),
                    "can_add": self.request.user.has_perm(crud.perm("add")),
                    "can_change": self.request.user.has_perm(crud.perm("change")),
                    "can_delete": self.request.user.has_perm(crud.perm("delete")),
                    "ns": ns,
                })
                return ctx

            def get_success_url(self):
                return reverse(f"{self.request.resolver_match.namespace}:{crud.url_name('list')}")

        class List(Base, ListView):
            permission_required = crud.perm("view")
            template_name = "crud/list.html"
            paginate_by = crud.paginate_by

            def get_queryset(self):
                qs = super().get_queryset()
                if crud.ordering:
                    qs = qs.order_by(*crud.ordering)
                q = self.request.GET.get("q", "").strip()
                if q and crud.search:
                    cond = Q()
                    for f in crud.search:
                        cond |= Q(**{f"{f}__icontains": q})
                    qs = qs.filter(cond)
                return qs

            def get_context_data(self, **kwargs):
                ctx = super().get_context_data(**kwargs)
                headers = crud.column_headers()
                ctx["headers"] = headers
                ctx["rows"] = [(obj, list(zip(headers, [crud.cell(obj, c) for c in crud.columns])))
                               for obj in ctx["object_list"]]
                return ctx

        class Create(Base, CreateView):
            permission_required = crud.perm("add")
            form_class = crud.form_class
            template_name = "form.html"

            def get_context_data(self, **kwargs):
                ctx = super().get_context_data(**kwargs)
                ctx["title"] = _("New %(name)s") % {"name": crud.model._meta.verbose_name}
                ctx["intro"] = crud.intro
                return ctx

            def form_valid(self, form):
                messages.success(self.request, _("Saved."))
                return super().form_valid(form)

        class Update(Base, UpdateView):
            permission_required = crud.perm("change")
            form_class = crud.form_class
            template_name = "form.html"

            def get_context_data(self, **kwargs):
                ctx = super().get_context_data(**kwargs)
                ctx["title"] = _("Edit %(name)s") % {"name": crud.model._meta.verbose_name}
                ctx["intro"] = crud.intro
                if self.request.user.has_perm(crud.perm("delete")):
                    ctx["delete_url"] = reverse(f"{ctx['ns']}:{crud.url_name('delete')}", args=[self.object.pk])
                return ctx

            def form_valid(self, form):
                messages.success(self.request, _("Saved."))
                return super().form_valid(form)

        class Delete(Base, DeleteView):
            permission_required = crud.perm("delete")
            template_name = "crud/confirm_delete.html"

            def form_valid(self, form):
                try:
                    return super().form_valid(form)
                except ProtectedError:
                    messages.error(self.request, _("This record is in use and cannot be deleted. "
                                                   "Mark it inactive instead."))
                    return redirect(self.get_success_url())

        return List, Create, Update, Delete

    def urls(self, prefix=None):
        prefix = prefix if prefix is not None else f"{self.name}s/"
        List, Create, Update, Delete = self.views()
        return [
            path(prefix, List.as_view(), name=self.url_name("list")),
            path(f"{prefix}new/", Create.as_view(), name=self.url_name("create")),
            path(f"{prefix}<int:pk>/", Update.as_view(), name=self.url_name("update")),
            path(f"{prefix}<int:pk>/delete/", Delete.as_view(), name=self.url_name("delete")),
        ]
