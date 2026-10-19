from django import forms

from apps.core.forms import DateInput

from .models import Employee


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            "code", "name", "phone", "photo", "designation", "default_project",
            "wage_type", "wage_rate", "overtime_hourly_rate", "pay_components",
            "date_joined", "date_of_birth", "address", "emergency_contact",
            "id_proof_type", "id_proof_number", "id_proof_file",
            "bank_account_name", "bank_account_number", "bank_ifsc", "upi_id",
            "user", "is_active", "notes",
        ]
        widgets = {
            "date_joined": DateInput(),
            "date_of_birth": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "pay_components": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pay_components"].queryset = self.fields["pay_components"].queryset.filter(
            is_active=True, apply_to_everyone=False
        )
