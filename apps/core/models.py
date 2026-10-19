from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class CompanySettings(models.Model):
    """
    Single row holding everything that differs between companies and countries.
    Nothing country-specific (currency, tax, statutory deductions) is hard-coded.
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

    name = models.CharField(_("company name"), max_length=200, default="My Construction Co.")
    address = models.TextField(_("address"), blank=True)
    phone = models.CharField(_("phone"), max_length=50, blank=True)
    email = models.EmailField(_("email"), blank=True)
    logo = models.ImageField(_("logo"), upload_to="company/", blank=True)

    currency_code = models.CharField(_("currency code"), max_length=3, default="INR")
    currency_symbol = models.CharField(_("currency symbol"), max_length=5, default="₹")

    tax_enabled = models.BooleanField(_("charge tax on quotations / POs"), default=False)
    tax_label = models.CharField(
        _("tax name"), max_length=30, default="GST", help_text=_("e.g. GST, VAT, Sales Tax")
    )
    tax_registration_number = models.CharField(_("tax registration number"), max_length=50, blank=True)
    default_tax_rate = models.DecimalField(
        _("default tax rate %"), max_digits=5, decimal_places=2, default=Decimal("18.00")
    )

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


class Project(models.Model):
    """A construction site / project. Attendance, stock and progress hang off this."""

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        ACTIVE = "active", _("Active")
        ON_HOLD = "on_hold", _("On hold")
        COMPLETED = "completed", _("Completed")

    name = models.CharField(_("project name"), max_length=200)
    code = models.CharField(_("code"), max_length=20, unique=True)
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
