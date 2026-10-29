from decimal import Decimal

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput
from apps.core.models import CompanySettings

from .models import Agreement, DocumentTemplate, PaymentMilestone, Quotation, QuotationLine, WorkItem


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ["client", "project", "date", "valid_until", "subject", "introduction", "discount_percent",
                  "terms", "status", "notes"]
        widgets = {
            "date": DateInput(), "valid_until": DateInput(),
            "introduction": forms.Textarea(attrs={"rows": 2}), "terms": forms.Textarea(attrs={"rows": 4}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class QuotationLineForm(forms.ModelForm):
    class Meta:
        model = QuotationLine
        fields = ["item", "description", "unit", "quantity", "rate", "tax_rate"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = WorkItem.objects.filter(is_active=True).select_related("unit")
        self.fields["item"].required = False
        self.fields["item"].widget.attrs["class"] = "item-select"
        self.fields["description"].required = False
        for name in ("quantity", "rate", "tax_rate"):
            self.fields[name].widget.attrs.update({"step": "any", "inputmode": "decimal", "class": name})
        if not CompanySettings.load().tax_enabled:
            self.fields["tax_rate"].widget = forms.HiddenInput()
            self.fields["tax_rate"].initial = 0

    def clean(self):
        data = super().clean()
        if data.get("quantity") and not data.get("description") and data.get("item"):
            data["description"] = data["item"].name + (f"\n{data['item'].description}" if data["item"].description else "")
            self.instance.description = data["description"]
        if data.get("quantity") and not data.get("description"):
            self.add_error("description", _("Enter a description or choose a rate item."))
        return data


class AgreementForm(forms.ModelForm):
    class Meta:
        model = Agreement
        fields = ["client", "project", "template", "title", "date", "contract_value", "start_date",
                  "completion_date", "site_address", "retention_percent", "status"]
        widgets = {"date": DateInput(), "start_date": DateInput(), "completion_date": DateInput(),
                   "site_address": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = DocumentTemplate.objects.filter(is_active=True)
        if not self.instance.pk and not self.initial.get("template"):
            self.initial["template"] = DocumentTemplate.objects.filter(is_active=True, is_default=True).first()


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = PaymentMilestone
        fields = ["description", "percent"]
        widgets = {"percent": forms.NumberInput(attrs={"step": "any", "class": "percent"})}


class BaseMilestoneFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        total = sum((f.cleaned_data.get("percent") or Decimal("0")) for f in self.forms
                    if f.cleaned_data and not f.cleaned_data.get("DELETE"))
        if total > 100:
            raise forms.ValidationError(_("Payment milestones add up to %(t)s%%, more than 100%%.") % {"t": total})


MilestoneFormSet = forms.formset_factory(MilestoneForm, formset=BaseMilestoneFormSet, extra=2, can_delete=True)


class AgreementTextForm(forms.ModelForm):
    class Meta:
        model = Agreement
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 28, "style": "font-family:monospace"})}
