from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput
from apps.core.models import CompanySettings

from .models import (GoodsReceipt, GoodsReceiptLine, Location, Material, MaterialIssue, MaterialIssueLine,
                     PurchaseOrder, PurchaseOrderLine, StockAdjustment, StockAdjustmentLine, StockTransfer,
                     StockTransferLine, Supplier)


def active_locations():
    return Location.objects.filter(is_active=True)


class HeaderForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "date" in self.fields and not self.initial.get("date"):
            self.initial["date"] = timezone.localdate()
        for name, field in self.fields.items():
            if isinstance(field, forms.ModelChoiceField) and field.queryset.model is Location:
                field.queryset = active_locations()
            if isinstance(field, forms.ModelChoiceField) and field.queryset.model is Supplier:
                field.queryset = Supplier.objects.filter(is_active=True)


class LineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "material" in self.fields:
            self.fields["material"].queryset = Material.objects.filter(is_active=True).select_related("unit")
            self.fields["material"].widget.attrs["class"] = "material-select"
        for name in ("quantity", "rate", "tax_rate"):
            if name in self.fields:
                self.fields[name].widget.attrs.update({"step": "any", "inputmode": "decimal", "class": name})
        if "tax_rate" in self.fields and not CompanySettings.load().tax_enabled:
            self.fields["tax_rate"].widget = forms.HiddenInput()
            self.fields["tax_rate"].initial = 0


class PurchaseOrderForm(HeaderForm):
    class Meta:
        model = PurchaseOrder
        fields = ["date", "supplier", "location", "expected_date", "notes", "terms"]
        widgets = {"date": DateInput(), "expected_date": DateInput(),
                   "notes": forms.Textarea(attrs={"rows": 2}), "terms": forms.Textarea(attrs={"rows": 3})}


class PurchaseOrderLineForm(LineForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ["material", "description", "quantity", "rate", "tax_rate"]


class GoodsReceiptForm(HeaderForm):
    class Meta:
        model = GoodsReceipt
        fields = ["date", "supplier", "location", "supplier_invoice_no", "vehicle_no", "notes"]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}


class GoodsReceiptLineForm(LineForm):
    class Meta:
        model = GoodsReceiptLine
        fields = ["material", "quantity", "rate", "order_line"]
        widgets = {"order_line": forms.HiddenInput()}

    def __init__(self, *args, purchase_order=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = PurchaseOrderLine.objects.filter(order=purchase_order) if purchase_order else PurchaseOrderLine.objects.none()
        self.fields["order_line"].queryset = qs
        self.fields["order_line"].required = False


class StockTransferForm(HeaderForm):
    class Meta:
        model = StockTransfer
        fields = ["date", "from_location", "to_location", "vehicle_no", "notes"]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}


class StockTransferLineForm(LineForm):
    class Meta:
        model = StockTransferLine
        fields = ["material", "quantity"]


class MaterialIssueForm(HeaderForm):
    class Meta:
        model = MaterialIssue
        fields = ["date", "location", "issued_to", "purpose", "notes"]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}


class MaterialIssueLineForm(LineForm):
    class Meta:
        model = MaterialIssueLine
        fields = ["material", "quantity"]


class StockAdjustmentForm(HeaderForm):
    class Meta:
        model = StockAdjustment
        fields = ["date", "location", "reason", "notes"]
        widgets = {"date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}


class StockAdjustmentLineForm(LineForm):
    class Meta:
        model = StockAdjustmentLine
        fields = ["material", "quantity", "rate"]
        help_texts = {"rate": _("Needed for opening stock so stock value is correct")}


def line_formset(form_class, extra=1):
    return forms.formset_factory(form_class, extra=extra, can_delete=True)


def cleaned_lines(formset):
    """Unsaved line objects from a valid formset, skipping blank, zero and deleted rows."""
    lines = []
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None) or {}
        if data.get("DELETE") or not data.get("material") or not data.get("quantity"):
            continue
        lines.append(form.save(commit=False))
    return lines
