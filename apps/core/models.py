import re
import zoneinfo
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop

TIMEZONE_CHOICES = [(tz, tz) for tz in sorted(zoneinfo.available_timezones()) if "/" in tz]

DEFAULT_QUOTATION_TERMS = """1. Prices are valid for the period stated above.
2. Any work not mentioned in this quotation will be charged extra.
3. Materials will be as per the specification agreed with the client.
4. Payment as per the agreed schedule."""

DEFAULT_PO_TERMS = """1. Please mention the PO number on your invoice and delivery challan.
2. Material must match the specification; rejected material will be returned at supplier cost.
3. Payment as per agreed credit terms after receipt of material and invoice."""


class CompanySettings(models.Model):
    """
    Single row holding everything that differs between client companies and
    countries. Nothing company- or country-specific is hard-coded, so the same
    product can be deployed for any client and set up from the screens.
    """

    WEEKDAYS = [
        (0, _("Monday")),
        (1, _("Tuesday")),
        (2, _("Wednesday")),
        (3, _("Thursday")),
        (4, _("Friday")),
        (5, _("Saturday")),
        (6, _("Sunday")),
    ]
    MONTHS = [(i, _(m)) for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"], start=1)]

    # Company profile
    name = models.CharField(_("company name"), max_length=200, default="My Construction Co.")
    address = models.TextField(_("address"), blank=True)
    phone = models.CharField(_("phone"), max_length=50, blank=True)
    email = models.EmailField(_("email"), blank=True)
    website = models.CharField(_("website"), max_length=100, blank=True)
    logo = models.ImageField(_("logo"), upload_to="company/", blank=True)
    brand_color = models.CharField(
        _("brand colour"), max_length=7, default="#d97706",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a colour like #d97706"))],
    )
    timezone = models.CharField(_("time zone"), max_length=50, choices=TIMEZONE_CHOICES, default="Asia/Kolkata")
    financial_year_start_month = models.PositiveSmallIntegerField(
        _("financial year starts in"), choices=MONTHS, default=4)

    # Modules – switch off what a client has not bought / does not need
    module_attendance = models.BooleanField(_("attendance"), default=True)
    module_payroll = models.BooleanField(_("salary / payroll"), default=True)
    module_inventory = models.BooleanField(_("inventory & purchase"), default=True)
    module_progress = models.BooleanField(_("building progress"), default=True)
    module_documents = models.BooleanField(_("quotations & agreements"), default=True)

    # Money & tax
    currency_code = models.CharField(_("currency code"), max_length=3, default="INR")
    currency_symbol = models.CharField(_("currency symbol"), max_length=5, default="₹")
    number_grouping = models.CharField(
        _("number format"), max_length=13, default="international",
        choices=[("international", _("1,234,567.00 (international)")), ("indian", _("12,34,567.00 (Indian lakh)"))])
    tax_enabled = models.BooleanField(_("charge tax on quotations / POs"), default=False)
    tax_label = models.CharField(
        _("tax name"), max_length=30, default="GST", help_text=_("e.g. GST, VAT, Sales Tax")
    )
    tax_registration_number = models.CharField(_("tax registration number"), max_length=50, blank=True)
    tax_code_label = models.CharField(_("item tax code name"), max_length=20, default="HSN/SAC",
                                      help_text=_("Shown on materials and quotations, e.g. HSN/SAC"))
    default_tax_rate = models.DecimalField(
        _("default tax rate %"), max_digits=5, decimal_places=2, default=Decimal("18.00")
    )
    bank_details = models.TextField(_("bank details for clients"), blank=True,
                                    help_text=_("Printed on quotations so clients can pay you"))

    # Documents
    signatory_name = models.CharField(_("authorised signatory"), max_length=100, blank=True)
    signatory_designation = models.CharField(_("signatory designation"), max_length=100, blank=True)
    document_footer = models.CharField(_("document footer"), max_length=200, blank=True)
    quotation_validity_days = models.PositiveSmallIntegerField(_("quotation valid for (days)"), default=30)
    quotation_terms = models.TextField(_("default quotation terms"), blank=True, default=DEFAULT_QUOTATION_TERMS)
    po_terms = models.TextField(_("default purchase order terms"), blank=True, default=DEFAULT_PO_TERMS)

    # Inventory
    allow_negative_stock = models.BooleanField(
        _("allow stock to go below zero"), default=False,
        help_text=_("Keep off so issues and transfers cannot use material that was never received"))

    # Payroll & attendance
    working_hours_per_day = models.DecimalField(
        _("working hours per day"), max_digits=4, decimal_places=2, default=Decimal("8.00")
    )
    overtime_multiplier = models.DecimalField(
        _("overtime pay multiplier"),
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text=_("1.00 = normal hourly rate, 1.50 = time and a half, 2.00 = double"),
    )
    weekly_off_day = models.PositiveSmallIntegerField(_("weekly off day"), choices=WEEKDAYS, default=6)
    monthly_salary_basis = models.CharField(
        _("monthly salary per-day basis"),
        max_length=10,
        choices=[
            ("calendar", _("Calendar days in month")),
            ("working", _("Working days (excluding weekly off)")),
            ("fixed30", _("Fixed 30 days")),
        ],
        default="calendar",
    )
    paid_weekly_off_for_monthly = models.BooleanField(
        _("monthly staff are paid for weekly off days"), default=True
    )
    paid_leave_for_monthly = models.BooleanField(
        _("approved leave is paid for monthly staff"), default=True
    )
    attendance_geofence_required = models.BooleanField(
        _("self check-in must be inside the site radius"), default=True
    )
    attendance_selfie_required = models.BooleanField(_("self check-in needs a photo"), default=True)

    # Security
    login_max_attempts = models.PositiveSmallIntegerField(
        _("wrong password attempts before lock"), default=5, validators=[MinValueValidator(3)])
    login_lockout_minutes = models.PositiveSmallIntegerField(_("lock time (minutes)"), default=15)

    class Meta:
        verbose_name = _("company settings")
        verbose_name_plural = _("company settings")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def module_enabled(self, key):
        return getattr(self, f"module_{key}", True)


class Unit(models.Model):
    """Units of measure used by materials and quotations (Bag, Kg, Cft, Sqft, Nos …)."""

    name = models.CharField(_("name"), max_length=50, unique=True)
    symbol = models.CharField(_("symbol"), max_length=15, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("unit")
        verbose_name_plural = _("units")

    def __str__(self):
        return self.symbol


class NumberSequence(models.Model):
    """
    Configurable document numbering, e.g. PO/{FY}/{SEQ} → PO/2026-27/0001.
    Tokens: {FY} financial year, {YYYY} {YY} year, {MM} month, {SEQ} running number.
    The running number restarts when the year / month in the pattern changes.
    """

    DEFAULTS = {
        "purchase_order": (gettext_noop("Purchase order"), "PO/{FY}/{SEQ}"),
        "goods_receipt": (gettext_noop("Goods receipt"), "GRN/{FY}/{SEQ}"),
        "stock_transfer": (gettext_noop("Stock transfer"), "TRF/{FY}/{SEQ}"),
        "material_issue": (gettext_noop("Material issue"), "ISS/{FY}/{SEQ}"),
        "stock_adjustment": (gettext_noop("Stock adjustment"), "ADJ/{FY}/{SEQ}"),
        "quotation": (gettext_noop("Quotation"), "QT/{FY}/{SEQ}"),
        "agreement": (gettext_noop("Agreement"), "AGR/{FY}/{SEQ}"),
    }

    key = models.CharField(max_length=40, unique=True, editable=False)
    label = models.CharField(_("document"), max_length=60, editable=False)
    pattern = models.CharField(_("number format"), max_length=60,
                               help_text=_("Use {FY}, {YYYY}, {YY}, {MM} and {SEQ}"))
    padding = models.PositiveSmallIntegerField(_("digits in running number"), default=4,
                                               validators=[MaxValueValidator(10)])
    next_value = models.PositiveIntegerField(_("next running number"), default=1)
    period = models.CharField(max_length=20, blank=True, editable=False)

    class Meta:
        ordering = ["label"]
        verbose_name = _("number series")
        verbose_name_plural = _("number series")

    def __str__(self):
        return self.label

    @staticmethod
    def financial_year(day, start_month):
        start_year = day.year if day.month >= start_month else day.year - 1
        if start_month == 1:
            return str(start_year)
        return f"{start_year}-{str(start_year + 1)[-2:]}"

    def period_for(self, day, start_month):
        if "{FY}" in self.pattern:
            return self.financial_year(day, start_month)
        if "{MM}" in self.pattern:
            return day.strftime("%Y-%m")
        if "{YYYY}" in self.pattern or "{YY}" in self.pattern:
            return str(day.year)
        return ""

    def render(self, value, day, start_month):
        tokens = {
            "FY": self.financial_year(day, start_month),
            "YYYY": str(day.year),
            "YY": str(day.year)[-2:],
            "MM": f"{day.month:02d}",
            "SEQ": str(value).zfill(self.padding),
        }
        return re.sub(r"\{(FY|YYYY|YY|MM|SEQ)\}", lambda m: tokens[m.group(1)], self.pattern)

    @classmethod
    def ensure_defaults(cls):
        for key, (label, pattern) in cls.DEFAULTS.items():
            cls.objects.get_or_create(key=key, defaults={"label": label, "pattern": pattern})

    @classmethod
    def next_number(cls, key, day=None):
        day = day or timezone.localdate()
        start_month = CompanySettings.load().financial_year_start_month
        with transaction.atomic():
            label, pattern = cls.DEFAULTS[key]
            cls.objects.get_or_create(key=key, defaults={"label": label, "pattern": pattern})
            seq = cls.objects.select_for_update().get(key=key)
            period = seq.period_for(day, start_month)
            if period != seq.period:
                seq.period = period
                seq.next_value = 1
            number = seq.render(seq.next_value, day, start_month)
            seq.next_value += 1
            seq.save(update_fields=["period", "next_value"])
            return number


class Project(models.Model):
    """A construction site / project. Attendance, stock and progress hang off this."""

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        ACTIVE = "active", _("Active")
        ON_HOLD = "on_hold", _("On hold")
        COMPLETED = "completed", _("Completed")

    name = models.CharField(_("project name"), max_length=200)
    code = models.CharField(_("code"), max_length=20, unique=True)
    client = models.ForeignKey("documents.Client", on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="projects", verbose_name=_("client"))
    client_name = models.CharField(_("client name"), max_length=200, blank=True)
    client_phone = models.CharField(_("client phone"), max_length=30, blank=True)
    address = models.TextField(_("site address"), blank=True)
    latitude = models.DecimalField(_("latitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(_("longitude"), max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(
        _("check-in radius (metres)"), default=200, validators=[MinValueValidator(20), MaxValueValidator(5000)]
    )
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    expected_end_date = models.DateField(_("expected end date"), null=True, blank=True)
    contract_value = models.DecimalField(_("contract value"), max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("project / site")
        verbose_name_plural = _("projects / sites")

    def __str__(self):
        return f"{self.code} – {self.name}"

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def client_display(self):
        return self.client.name if self.client_id else self.client_name


class AuditLog(models.Model):
    """Who changed what and when – useful when there is a dispute about attendance or pay."""

    class Action(models.TextChoices):
        CREATE = "create", _("Created")
        UPDATE = "update", _("Changed")
        DELETE = "delete", _("Deleted")

    at = models.DateTimeField(_("time"), auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="+", verbose_name=_("user"))
    action = models.CharField(_("action"), max_length=10, choices=Action.choices)
    model = models.CharField(_("record type"), max_length=100)
    object_id = models.CharField(max_length=40)
    object_repr = models.CharField(_("record"), max_length=200)
    changes = models.JSONField(_("changes"), default=dict, blank=True)

    class Meta:
        ordering = ["-at", "-pk"]
        verbose_name = _("audit log entry")
        verbose_name_plural = _("audit log")

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.user} {self.action} {self.object_repr}"
