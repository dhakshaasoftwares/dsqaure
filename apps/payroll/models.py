from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PayComponent(models.Model):
    """
    A configurable allowance, deduction or employer contribution.

    Statutory items (PF, ESI, professional tax, social security, ...) are just
    rows here, so each company decides which ones exist and how they are worked
    out. Nothing is tied to one country.
    """

    class Kind(models.TextChoices):
        EARNING = "earning", _("Earning / allowance")
        DEDUCTION = "deduction", _("Deduction from employee")
        EMPLOYER = "employer", _("Employer contribution (not deducted)")

    class Method(models.TextChoices):
        FIXED = "fixed", _("Fixed amount per payroll")
        PER_DAY = "per_day", _("Amount per day worked")
        PERCENT_BASIC = "pct_basic", _("Percentage of earned wage")
        PERCENT_GROSS = "pct_gross", _("Percentage of gross pay")

    class AppliesTo(models.TextChoices):
        ALL = "all", _("Daily and monthly staff")
        DAILY = "daily", _("Daily wage staff only")
        MONTHLY = "monthly", _("Monthly staff only")

    name = models.CharField(_("name"), max_length=100)
    code = models.SlugField(_("short code"), max_length=30, unique=True)
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices)
    method = models.CharField(_("calculation"), max_length=10, choices=Method.choices)
    value = models.DecimalField(
        _("amount or percentage"), max_digits=10, decimal_places=2,
        help_text=_("An amount for fixed / per day, or a percentage such as 12 for 12%"),
    )
    base_ceiling = models.DecimalField(
        _("calculate on at most"), max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=_("Percentage is applied to the smaller of the wage and this amount (e.g. a PF wage ceiling)"),
    )
    eligible_max_gross = models.DecimalField(
        _("only if gross pay is at most"), max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=_("Skip this rule when gross pay is above this amount (e.g. an ESI limit)"),
    )
    max_amount = models.DecimalField(_("maximum amount"), max_digits=12, decimal_places=2, null=True, blank=True)
    applies_to = models.CharField(_("applies to"), max_length=10, choices=AppliesTo.choices, default=AppliesTo.ALL)
    apply_to_everyone = models.BooleanField(
        _("apply to everyone automatically"), default=False,
        help_text=_("Otherwise it applies only to employees it is selected for"),
    )
    round_to_whole = models.BooleanField(_("round to whole number"), default=True)
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("display order"), default=0)

    class Meta:
        ordering = ["kind", "sort_order", "name"]
        verbose_name = _("pay component")
        verbose_name_plural = _("pay components")

    def __str__(self):
        return self.name


class SalaryAdvance(models.Model):
    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="advances", verbose_name=_("employee")
    )
    date = models.DateField(_("date"))
    amount = models.DecimalField(_("amount"), max_digits=10, decimal_places=2)
    installment = models.DecimalField(
        _("recover per payroll"), max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Leave blank to recover the full balance in the next payroll"),
    )
    recovered_amount = models.DecimalField(_("recovered so far"), max_digits=10, decimal_places=2, default=0)
    reason = models.CharField(_("reason"), max_length=200, blank=True)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["date", "pk"]
        verbose_name = _("salary advance")
        verbose_name_plural = _("salary advances")

    def __str__(self):
        return f"{self.employee} {self.date} {self.amount}"

    @property
    def balance(self):
        return self.amount - self.recovered_amount


class PayrollRun(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        FINALIZED = "finalized", _("Finalized")

    period_start = models.DateField(_("from"))
    period_end = models.DateField(_("to"))
    wage_type = models.CharField(
        _("staff"), max_length=10, blank=True,
        choices=[("", _("All staff")), ("daily", _("Daily wage")), ("monthly", _("Monthly salary"))],
    )
    project = models.ForeignKey(
        "core.Project", on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("site"), help_text=_("Leave blank for all sites"),
    )
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_end", "-pk"]
        verbose_name = _("payroll run")
        verbose_name_plural = _("payroll runs")

    def __str__(self):
        return f"{self.period_start} → {self.period_end}"

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    @property
    def total_net(self):
        return sum((p.net_pay for p in self.payslips.all()), Decimal("0"))


class Payslip(models.Model):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("employees.Employee", on_delete=models.PROTECT, related_name="payslips")
    wage_type = models.CharField(max_length=10)
    wage_rate = models.DecimalField(max_digits=10, decimal_places=2)
    days_worked = models.DecimalField(max_digits=5, decimal_places=1)
    paid_days = models.DecimalField(max_digits=5, decimal_places=1)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2)
    basic_pay = models.DecimalField(max_digits=12, decimal_places=2)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2)
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2)
    advance_recovery = models.DecimalField(max_digits=12, decimal_places=2)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2)
    employer_contributions = models.DecimalField(max_digits=12, decimal_places=2)
    # [{"name": ..., "kind": "earning|deduction|employer", "amount": "123.00"}]
    lines = models.JSONField(default=list)
    # [{"advance_id": 1, "amount": "500.00"}] – applied to advances on finalize
    advance_allocations = models.JSONField(default=list)

    class Meta:
        ordering = ["employee__name"]
        constraints = [models.UniqueConstraint(fields=["run", "employee"], name="one_payslip_per_run")]

    def __str__(self):
        return f"{self.employee} – {self.run}"

    @property
    def all_deductions(self):
        return self.total_deductions + self.advance_recovery

    def lines_of(self, kind):
        return [line for line in self.lines if line["kind"] == kind]

    @property
    def earning_lines(self):
        return self.lines_of("earning")

    @property
    def deduction_lines(self):
        return self.lines_of("deduction")

    @property
    def employer_lines(self):
        return self.lines_of("employer")
