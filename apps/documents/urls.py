from django import forms
from django.urls import path
from django.utils.translation import gettext_lazy as _

from apps.core.crud import Crud

from . import views
from .models import Client, DocumentTemplate, WorkItem

app_name = "documents"

clients = Crud(
    Client, "client", fields=["name", "contact_person", "phone", "email", "address", "tax_number", "notes"],
    columns=["name", "contact_person", "phone", "email"], search=["name", "contact_person", "phone"],
    widgets={"address": forms.Textarea(attrs={"rows": 2}), "notes": forms.Textarea(attrs={"rows": 2})},
)
work_items = Crud(
    WorkItem, "work_item",
    fields=["category", "name", "description", "unit", "rate", "tax_code", "tax_rate", "is_active"],
    columns=["category", "name", "unit", "rate", "tax_rate", "is_active"], search=["name", "category"],
    widgets={"description": forms.Textarea(attrs={"rows": 3})},
    intro=_("Your standard items and rates. Pick them when making a quotation; you can still change the rate."),
)
templates = Crud(
    DocumentTemplate, "template", fields=["name", "body", "is_default", "is_active"],
    columns=["name", "is_default", "is_active"], search=["name"],
    widgets={"body": forms.Textarea(attrs={"rows": 24, "style": "font-family:monospace"})},
    intro=_("Write your agreement wording. Placeholders like {client_name} are filled in automatically – "
            "see the placeholder list."),
)

urlpatterns = [
    path("quotations/", views.quotation_list, name="quotation_list"),
    path("quotations/new/", views.quotation_create, name="quotation_create"),
    path("quotations/<int:pk>/", views.quotation_detail, name="quotation_detail"),
    path("quotations/<int:pk>/edit/", views.quotation_update, name="quotation_update"),
    path("quotations/<int:pk>/status/", views.quotation_status, name="quotation_status"),
    path("quotations/<int:pk>/pdf/", views.quotation_pdf, name="quotation_pdf"),
    path("agreements/", views.agreement_list, name="agreement_list"),
    path("agreements/new/", views.agreement_create, name="agreement_create"),
    path("agreements/<int:pk>/", views.agreement_detail, name="agreement_detail"),
    path("agreements/<int:pk>/edit/", views.agreement_update, name="agreement_update"),
    path("agreements/<int:pk>/text/", views.agreement_text, name="agreement_text"),
    path("agreements/<int:pk>/pdf/", views.agreement_pdf, name="agreement_pdf"),
    path("templates/placeholders/", views.placeholders, name="placeholders"),
    *clients.urls("clients/"),
    *work_items.urls("rates/"),
    *templates.urls("templates/"),
]
