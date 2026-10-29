from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput
from apps.core.models import CompanySettings

from .models import ClientPayment, Invoice, InvoiceLine


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["client", "project", "agreement", "milestone", "title", "date", "due_date", "inter_state",
                  "retention_percent", "terms", "notes"]
        widgets = {"date": DateInput(), "due_date": DateInput(), "terms": forms.Textarea(attrs={"rows": 2}),
                   "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = CompanySettings.load()
        if not (company.tax_enabled and company.tax_split_enabled):
            self.fields["inter_state"].widget = forms.HiddenInput()
        self.fields["milestone"].queryset = self.fields["milestone"].queryset.select_related("agreement")
        self.fields["milestone"].label_from_instance = lambda m: f"{m.agreement.number} – {m.description}"

    def clean(self):
        data = super().clean()
        milestone, agreement = data.get("milestone"), data.get("agreement")
        if milestone and agreement and milestone.agreement_id != agreement.pk:
            self.add_error("milestone", forms.ValidationError(_("This milestone belongs to another agreement.")))
        if milestone and not agreement:
            data["agreement"] = milestone.agreement
            self.instance.agreement = milestone.agreement
        return data


class InvoiceLineForm(forms.ModelForm):
    class Meta:
        model = InvoiceLine
        fields = ["description", "tax_code", "quantity", "unit", "rate", "tax_rate"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("quantity", "rate", "tax_rate"):
            self.fields[name].widget.attrs.update({"step": "any", "inputmode": "decimal", "class": name})
        company = CompanySettings.load()
        if not company.tax_enabled:
            self.fields["tax_rate"].widget = forms.HiddenInput()
            self.fields["tax_code"].widget = forms.HiddenInput()


InvoiceLineFormSet = forms.formset_factory(InvoiceLineForm, extra=2, can_delete=True)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = ClientPayment
        fields = ["date", "amount", "mode", "reference", "notes"]
        widgets = {"date": DateInput()}
