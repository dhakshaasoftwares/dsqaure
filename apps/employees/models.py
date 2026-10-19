from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Employee(models.Model):
    class WageType(models.TextChoices):
        DAILY = "daily", _("Daily wage")
        MONTHLY = "monthly", _("Monthly salary")

    code = models.CharField(_("employee code"), max_length=20, unique=True)
    name = models.CharField(_("name"), max_length=150)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    photo = models.ImageField(_("photo"), upload_to="employees/photos/", blank=True)
    designation = models.CharField(_("designation / trade"), max_length=100, blank=True,
                                   help_text=_("e.g. Mason, Helper, Carpenter, Site Engineer"))
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    address = models.TextField(_("address"), blank=True)
    id_proof_type = models.CharField(_("ID proof type"), max_length=50, blank=True)
    id_proof_number = models.CharField(_("ID proof number"), max_length=50, blank=True)
    id_proof_file = models.FileField(_("ID proof file"), upload_to="employees/id/", blank=True)
    emergency_contact = models.CharField(_("emergency contact"), max_length=100, blank=True)

    wage_type = models.CharField(_("wage type"), max_length=10, choices=WageType.choices, default=WageType.DAILY)
    wage_rate = models.DecimalField(
        _("wage rate"), max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text=_("Per day for daily wage, per month for monthly salary"),
    )
    overtime_hourly_rate = models.DecimalField(
        _("overtime hourly rate"), max_digits=8, decimal_places=2, null=True, blank=True,
        help_text=_("Leave blank to calculate from wage and company overtime settings"),
    )
    pay_components = models.ManyToManyField(
        "payroll.PayComponent", blank=True, verbose_name=_("allowances / deductions"),
        help_text=_("Extra pay rules applied to this employee in addition to the ones marked 'apply to everyone'"),
    )

    bank_account_name = models.CharField(_("account holder name"), max_length=150, blank=True)
    bank_account_number = models.CharField(_("account number"), max_length=40, blank=True)
    bank_ifsc = models.CharField(_("bank / branch code"), max_length=20, blank=True)
    upi_id = models.CharField(_("UPI / mobile wallet"), max_length=100, blank=True)

    default_project = models.ForeignKey(
        "core.Project", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employees", verbose_name=_("assigned site"),
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="employee", verbose_name=_("login account"),
    )
    date_joined = models.DateField(_("date joined"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("employee")
        verbose_name_plural = _("employees")

    def __str__(self):
        return f"{self.name} ({self.code})"
