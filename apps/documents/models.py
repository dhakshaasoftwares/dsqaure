from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

ZERO = Decimal("0")
CENT = Decimal("0.01")
MONEY = dict(max_digits=14, decimal_places=2)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class Client(models.Model):
    name = models.CharField(_("name"), max_length=200)
    contact_person = models.CharField(_("contact person"), max_length=100, blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    tax_number = models.CharField(_("tax registration number"), max_length=50, blank=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("client")
        verbose_name_plural = _("clients")

    def __str__(self):
        return self.name


class WorkItem(models.Model):
    """Rate library for quotations (e.g. 'Brickwork in CM 1:6' per Cft)."""

    category = models.CharField(_("group"), max_length=100, blank=True,
                                help_text=_("e.g. Civil, Electrical, Plumbing"))
    name = models.CharField(_("item"), max_length=200)
    description = models.TextField(_("specification"), blank=True)
    unit = models.ForeignKey("core.Unit", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("unit"))
    rate = models.DecimalField(_("rate"), default=ZERO, **MONEY)
    tax_code = models.CharField(_("tax code (HSN/SAC)"), max_length=20, blank=True)
    tax_rate = models.DecimalField(_("tax rate %"), max_digits=5, decimal_places=2, default=ZERO)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["category", "name"]
        verbose_name = _("rate item")
        verbose_name_plural = _("rate items")

    def __str__(self):
        return f"{self.name} ({self.unit or '-'})"


class Quotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SENT = "sent", _("Sent to client")
        ACCEPTED = "accepted", _("Accepted")
        REJECTED = "rejected", _("Rejected")

    number = models.CharField(_("quotation no."), max_length=40, unique=True, editable=False)
    date = models.DateField(_("date"))
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="quotations", verbose_name=_("client"))
    project = models.ForeignKey("core.Project", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="quotations", verbose_name=_("project"))
    subject = models.CharField(_("subject"), max_length=200,
                               help_text=_("e.g. Construction of G+1 residential building"))
    introduction = models.TextField(_("introduction"), blank=True)
    discount_percent = models.DecimalField(_("discount %"), max_digits=5, decimal_places=2, default=ZERO,
                                           validators=[MinValueValidator(0), MaxValueValidator(100)])
    terms = models.TextField(_("terms & conditions"), blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(_("internal notes"), blank=True, help_text=_("Not printed"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("quotation")
        verbose_name_plural = _("quotations")

    def __str__(self):
        return self.number

    def totals(self, tax_enabled=True):
        lines = list(self.lines.all())
        factor = (100 - self.discount_percent) / 100
        subtotal = sum((l.amount for l in lines), ZERO)
        discount = money(subtotal * self.discount_percent / 100)
        tax = sum((l.amount * factor * l.tax_rate / 100 for l in lines), ZERO) if tax_enabled else ZERO
        tax = money(tax)
        return {"subtotal": money(subtotal), "discount": discount, "taxable": money(subtotal - discount),
                "tax": tax, "total": money(subtotal - discount + tax)}


class QuotationLine(models.Model):
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name="lines")
    order = models.PositiveSmallIntegerField(default=0)
    item = models.ForeignKey(WorkItem, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("rate item"))
    description = models.TextField(_("description"))
    unit = models.CharField(_("unit"), max_length=15, blank=True)
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3)
    rate = models.DecimalField(_("rate"), **MONEY)
    tax_rate = models.DecimalField(_("tax %"), max_digits=5, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["order", "pk"]

    @property
    def amount(self):
        return money(self.quantity * self.rate)


class DocumentTemplate(models.Model):
    """Agreement wording with {placeholders}; each client company writes its own."""

    name = models.CharField(_("name"), max_length=150)
    body = models.TextField(_("text"), help_text=_("Lines starting with # become headings. Use the placeholders listed below."))
    is_default = models.BooleanField(_("default"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name = _("agreement template")
        verbose_name_plural = _("agreement templates")

    def __str__(self):
        return self.name


class Agreement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        SIGNED = "signed", _("Signed")
        CANCELLED = "cancelled", _("Cancelled")

    number = models.CharField(_("agreement no."), max_length=40, unique=True, editable=False)
    date = models.DateField(_("agreement date"))
    title = models.CharField(_("title"), max_length=200, default="Construction Agreement")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="agreements", verbose_name=_("client"))
    project = models.ForeignKey("core.Project", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="agreements", verbose_name=_("project"))
    quotation = models.ForeignKey(Quotation, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="agreements", verbose_name=_("quotation"))
    template = models.ForeignKey(DocumentTemplate, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name=_("template"))
    contract_value = models.DecimalField(_("contract value"), **MONEY)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    completion_date = models.DateField(_("completion date"), null=True, blank=True)
    site_address = models.TextField(_("site address"), blank=True)
    retention_percent = models.DecimalField(_("retention %"), max_digits=5, decimal_places=2, default=ZERO,
                                            validators=[MinValueValidator(0), MaxValueValidator(100)],
                                            help_text=_("Held back from each bill until handover, if agreed"))
    body = models.TextField(_("agreement text"), blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("agreement")
        verbose_name_plural = _("agreements")

    def __str__(self):
        return self.number


class PaymentMilestone(models.Model):
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE, related_name="milestones")
    order = models.PositiveSmallIntegerField(default=0)
    description = models.CharField(_("stage / milestone"), max_length=200)
    percent = models.DecimalField(_("share of value (%)"), max_digits=5, decimal_places=2,
                                  validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        ordering = ["order", "pk"]

    @property
    def amount(self):
        return money(self.agreement.contract_value * self.percent / 100)
