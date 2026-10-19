from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput

from .models import PayComponent, PayrollRun, SalaryAdvance


class PayrollRunForm(forms.ModelForm):
    class Meta:
        model = PayrollRun
        fields = ["period_start", "period_end", "wage_type", "project"]
        widgets = {"period_start": DateInput(), "period_end": DateInput()}

    def clean(self):
        data = super().clean()
        start, end = data.get("period_start"), data.get("period_end")
        if start and end:
            if end < start:
                raise forms.ValidationError(_("'To' date must be after 'From' date."))
            if (end - start).days > 31:
                raise forms.ValidationError(_("A payroll period can be at most one month."))
        return data


class SalaryAdvanceForm(forms.ModelForm):
    class Meta:
        model = SalaryAdvance
        fields = ["employee", "date", "amount", "installment", "reason"]
        widgets = {"date": DateInput()}


class PayComponentForm(forms.ModelForm):
    class Meta:
        model = PayComponent
        fields = ["name", "code", "kind", "method", "value", "base_ceiling", "eligible_max_gross",
                  "max_amount", "applies_to", "apply_to_everyone", "round_to_whole", "is_active", "sort_order"]
