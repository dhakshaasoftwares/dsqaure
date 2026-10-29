from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

ZERO = Decimal("0")
CENT = Decimal("0.01")
MONEY = dict(max_digits=14, decimal_places=2)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class Invoice(models.Model):
    """A bill to a client – usually a running bill for one payment milestone of an agreement."""

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ISSUED = "issued", _("Issued")
        CANCELLED = "cancelled", _("Cancelled")

    number = models.CharField(_("invoice no."), max_length=40, unique=True, null=True, blank=True, editable=False,
                              help_text=_("Given when the invoice is issued, so numbers have no gaps"))
    date = models.DateField(_("date"))
    due_date = models.DateField(_("due date"), null=True, blank=True)
    client = models.ForeignKey("documents.Client", on_delete=models.PROTECT, related_name="invoices",
                               verbose_name=_("client"))
    project = models.ForeignKey("core.Project", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="invoices", verbose_name=_("project"))
    agreement = models.ForeignKey("documents.Agreement", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="invoices", verbose_name=_("agreement"))
    milestone = models.ForeignKey("documents.PaymentMilestone", on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="invoices", verbose_name=_("payment milestone"))
    title = models.CharField(_("title"), max_length=200, help_text=_("e.g. Running bill 3 – roof slab"))
    inter_state = models.BooleanField(_("client is in another state / region"), default=False,
                                      help_text=_("Uses the single inter-state tax instead of the split tax"))
    retention_percent = models.DecimalField(_("retention %"), max_digits=5, decimal_places=2, default=ZERO,
                                            validators=[MinValueValidator(0), MaxValueValidator(100)],
                                            help_text=_("Amount held back by the client until handover"))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT,
                              editable=False)
    notes = models.TextField(_("notes"), blank=True)
    terms = models.TextField(_("terms"), blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")

    def __str__(self):
        return self.number or _("Draft invoice #%(pk)s") % {"pk": self.pk}

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    def amounts(self, company):
        """All the money figures for this invoice, using the company's tax settings."""
        lines = list(self.lines.all())
        subtotal = money(sum((l.amount for l in lines), ZERO))
        tax = money(sum((l.amount * l.tax_rate / 100 for l in lines), ZERO)) if company.tax_enabled else ZERO
        total = subtotal + tax
        retention = money(subtotal * self.retention_percent / 100)
        payable = total - retention
        paid = self.payments.aggregate(s=Sum("amount"))["s"] or ZERO
        return {
            "subtotal": subtotal, "tax": tax, "tax_parts": self.tax_parts(company, tax), "total": total,
            "retention": retention, "payable": payable, "paid": paid, "balance": payable - paid,
        }

    def tax_parts(self, company, tax):
        if not company.tax_enabled or not tax:
            return []
        labels = [x.strip() for x in company.tax_split_labels.split(",") if x.strip()]
        if company.tax_split_enabled and not self.inter_state and len(labels) == 2:
            first = money(tax / 2)
            return [(labels[0], first), (labels[1], tax - first)]
        label = company.tax_interstate_label if company.tax_split_enabled and self.inter_state else company.tax_label
        return [(label, tax)]

    def payment_state(self, company, today=None):
        if self.status != self.Status.ISSUED:
            return self.status
        a = self.amounts(company)
        if a["balance"] <= 0:
            return "paid"
        today = today or timezone.localdate()
        if self.due_date and self.due_date < today:
            return "overdue"
        return "partly_paid" if a["paid"] > 0 else "unpaid"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    order = models.PositiveSmallIntegerField(default=0)
    description = models.TextField(_("description"))
    tax_code = models.CharField(_("tax code"), max_length=20, blank=True)
    quantity = models.DecimalField(_("quantity"), max_digits=12, decimal_places=3, default=1)
    unit = models.CharField(_("unit"), max_length=15, blank=True, default="LS")
    rate = models.DecimalField(_("rate"), **MONEY)
    tax_rate = models.DecimalField(_("tax %"), max_digits=5, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["order", "pk"]

    @property
    def amount(self):
        return money(self.quantity * self.rate)


class ClientPayment(models.Model):
    class Mode(models.TextChoices):
        BANK = "bank", _("Bank transfer")
        UPI = "upi", _("UPI")
        CHEQUE = "cheque", _("Cheque")
        CASH = "cash", _("Cash")
        OTHER = "other", _("Other")

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments",
                                verbose_name=_("invoice"))
    date = models.DateField(_("date"), default=timezone.localdate)
    amount = models.DecimalField(_("amount"), **MONEY, validators=[MinValueValidator(Decimal("0.01"))])
    mode = models.CharField(_("mode"), max_length=10, choices=Mode.choices, default=Mode.BANK)
    reference = models.CharField(_("reference / cheque no."), max_length=100, blank=True)
    notes = models.CharField(_("notes"), max_length=200, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("client payment")
        verbose_name_plural = _("client payments")

    def __str__(self):
        return f"{self.date} {self.amount} – {self.invoice}"
