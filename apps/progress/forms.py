from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.forms import DateInput

from .models import ProjectStage


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/*", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


class ProgressUpdateForm(forms.Form):
    stage = forms.ModelChoiceField(label=_("Stage"), queryset=ProjectStage.objects.none(), required=False)
    percent = forms.DecimalField(label=_("Stage now complete (%)"), min_value=0, max_value=100, required=False,
                                 widget=forms.NumberInput(attrs={"step": "5", "inputmode": "decimal"}))
    date = forms.DateField(label=_("Date"), widget=DateInput(), initial=timezone.localdate)
    note = forms.CharField(label=_("What was done"), widget=forms.Textarea(attrs={"rows": 2}), required=False)
    photos = MultipleImageField(label=_("Site photos"), required=False)

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stage"].queryset = project.stages.all() if project else ProjectStage.objects.none()

    def clean(self):
        data = super().clean()
        if data.get("percent") is not None and not data.get("stage"):
            self.add_error("stage", _("Choose the stage this percentage is for."))
        if not (data.get("note") or data.get("photos") or data.get("percent") is not None):
            raise forms.ValidationError(_("Enter a note, a percentage or at least one photo."))
        return data


class ProjectStageForm(forms.ModelForm):
    class Meta:
        model = ProjectStage
        fields = ["name", "order", "weight", "planned_start", "planned_end", "actual_start", "actual_end",
                  "percent", "notes"]
        widgets = {
            "planned_start": DateInput(), "planned_end": DateInput(), "actual_start": DateInput(),
            "actual_end": DateInput(), "notes": forms.Textarea(attrs={"rows": 2}),
        }
