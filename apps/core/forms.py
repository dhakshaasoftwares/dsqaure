from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _

from .models import CompanySettings, NumberSequence, Project
from .setup import COUNTRY_PRESETS


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class ColorInput(forms.TextInput):
    input_type = "color"


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "code", "client", "client_name", "client_phone", "address", "latitude", "longitude",
                  "geofence_radius_m", "status", "start_date", "expected_end_date", "contract_value"]
        widgets = {
            "start_date": DateInput(),
            "expected_end_date": DateInput(),
            "address": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {"client_name": _("Only needed if the client is not in the client list")}


class CompanySettingsForm(forms.ModelForm):
    """All company configuration, shown in sections."""

    email_password = forms.CharField(
        label=_("email password / app password"), required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text=_("Leave blank to keep the saved password. For Gmail use an 'app password'. "
                    "Placeholders for messages: {client} {document} {number} {amount} {company} {link}"))

    SECTIONS = [
        (_("Company profile & branding"),
         ["name", "address", "phone", "email", "website", "logo", "brand_color", "timezone",
          "financial_year_start_month"]),
        (_("Modules in use"),
         ["module_attendance", "module_payroll", "module_inventory", "module_progress", "module_documents", "module_billing"]),
        (_("Currency & tax"),
         ["currency_code", "currency_symbol", "number_grouping", "tax_enabled", "tax_label", "tax_registration_number",
          "tax_code_label", "default_tax_rate", "tax_split_enabled", "tax_split_labels", "tax_interstate_label",
          "currency_name", "currency_fraction_name", "bank_details"]),
        (_("Documents (quotations, agreements, POs)"),
         ["signatory_name", "signatory_designation", "document_footer", "quotation_validity_days",
          "quotation_terms", "po_terms", "invoice_due_days", "invoice_terms"]),
        (_("Attendance & salary"),
         ["working_hours_per_day", "overtime_multiplier", "weekly_off_day", "monthly_salary_basis",
          "paid_weekly_off_for_monthly", "paid_leave_for_monthly", "attendance_geofence_required",
          "attendance_selfie_required"]),
        (_("Email & WhatsApp"),
         ["email_host", "email_port", "email_username", "email_password", "email_use_tls", "email_use_ssl",
          "email_from_name", "email_from_address", "email_subject_template", "email_body_template",
          "whatsapp_template", "whatsapp_country_code", "share_link_days"]),
        (_("Inventory"), ["allow_negative_stock"]),
        (_("Security"), ["login_max_attempts", "login_lockout_minutes"]),
    ]

    class Meta:
        model = CompanySettings
        exclude = []
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "bank_details": forms.Textarea(attrs={"rows": 3}),
            "quotation_terms": forms.Textarea(attrs={"rows": 5}),
            "po_terms": forms.Textarea(attrs={"rows": 4}),
            "invoice_terms": forms.Textarea(attrs={"rows": 3}),
            "email_body_template": forms.Textarea(attrs={"rows": 5}),
            "whatsapp_template": forms.Textarea(attrs={"rows": 3}),
            "brand_color": ColorInput(),
        }

    def clean_email_password(self):
        from apps.sharing.services import encrypt_secret

        new = self.cleaned_data.get("email_password")
        return encrypt_secret(new) if new else self.instance.email_password

    def sections(self):
        for title, names in self.SECTIONS:
            yield title, [self[name] for name in names]


class NumberSequenceForm(forms.ModelForm):
    class Meta:
        model = NumberSequence
        fields = ["pattern", "padding", "next_value"]

    def clean_pattern(self):
        pattern = self.cleaned_data["pattern"]
        if "{SEQ}" not in pattern:
            raise forms.ValidationError(_("The format must contain {SEQ}."))
        return pattern


class SetupForm(forms.Form):
    company_name = forms.CharField(label=_("Company name"), max_length=200)
    phone = forms.CharField(label=_("Phone"), max_length=50, required=False)
    address = forms.CharField(label=_("Address"), widget=forms.Textarea(attrs={"rows": 2}), required=False)
    preset = forms.ChoiceField(
        label=_("Country preset"),
        choices=[("none", _("None – I will set currency and tax myself")), ("india", _("India (INR, GST, PF/ESI samples)"))],
        initial="india",
    )
    language = forms.ChoiceField(label=_("Your language"), choices=[("en", "English"), ("ta", "தமிழ்")])
    owner_name = forms.CharField(label=_("Your name"), max_length=150)
    username = forms.CharField(label=_("Owner username"), max_length=150)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput)
    password2 = forms.CharField(label=_("Repeat password"), widget=forms.PasswordInput)

    def clean_preset(self):
        value = self.cleaned_data["preset"]
        if value not in COUNTRY_PRESETS:
            raise forms.ValidationError(_("Unknown preset"))
        return value

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", _("The two passwords do not match."))
        elif data.get("password1"):
            try:
                validate_password(data["password1"])
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data
