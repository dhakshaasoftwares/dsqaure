from django import forms
from django.urls import path, re_path
from django.utils.translation import gettext_lazy as _

from apps.core.crud import Crud

from . import views
from .models import Location, Material, MaterialCategory, Supplier

app_name = "inventory"
KINDS = "|".join(views.DOCS)

materials = Crud(
    Material, "material",
    fields=["code", "name", "category", "unit", "tax_code", "tax_rate", "reorder_level", "last_purchase_rate",
            "is_active", "notes"],
    columns=["code", "name", "category", "unit", "reorder_level", "last_purchase_rate", "is_active"],
    search=["code", "name"], widgets={"notes": forms.Textarea(attrs={"rows": 2})},
)
suppliers = Crud(
    Supplier, "supplier",
    fields=["name", "contact_person", "phone", "email", "address", "tax_number", "payment_terms",
            "bank_details", "is_active"],
    columns=["name", "contact_person", "phone", "payment_terms", "is_active"],
    search=["name", "contact_person", "phone"],
    widgets={"address": forms.Textarea(attrs={"rows": 2}), "bank_details": forms.Textarea(attrs={"rows": 2})},
)
locations = Crud(
    Location, "location", fields=["name", "kind", "address", "is_active"],
    columns=["name", "kind", "is_active"], search=["name"],
    intro=_("Project sites are added automatically. Add godowns / central stores here."),
    widgets={"address": forms.Textarea(attrs={"rows": 2})},
)
categories = Crud(MaterialCategory, "category", fields=["name"], columns=["name"], search=["name"])

urlpatterns = [
    path("", views.stock, name="stock"),
    path("ledger/", views.ledger, name="ledger"),
    path("po/", views.po_list, name="po_list"),
    path("po/new/", views.po_create, name="po_create"),
    path("po/<int:pk>/", views.po_detail, name="po_detail"),
    path("po/<int:pk>/edit/", views.po_update, name="po_update"),
    path("po/<int:pk>/pdf/", views.po_pdf, name="po_pdf"),
    path("po/<int:pk>/action/", views.po_action, name="po_action"),
    *materials.urls("materials/"),
    *suppliers.urls("suppliers/"),
    *locations.urls("locations/"),
    *categories.urls("categories/"),
    # receipt / transfer / issue / adjustment share one set of screens
    re_path(rf"^(?P<kind>{KINDS})/list/$", views.doc_list, name="doc_list"),
    re_path(rf"^(?P<kind>{KINDS})/new/$", views.doc_create, name="doc_create"),
    re_path(rf"^(?P<kind>{KINDS})/(?P<pk>[0-9]+)/$", views.doc_detail, name="doc_detail"),
    re_path(rf"^(?P<kind>{KINDS})/(?P<pk>[0-9]+)/delete/$", views.doc_delete, name="doc_delete"),
]
