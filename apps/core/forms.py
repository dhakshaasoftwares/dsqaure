from django import forms

from .models import CompanySettings, Project


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "code", "client_name", "client_phone", "address", "latitude", "longitude",
                  "geofence_radius_m", "status", "start_date", "expected_end_date", "contract_value"]
        widgets = {
            "start_date": DateInput(),
            "expected_end_date": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
        }


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        exclude = []
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}
