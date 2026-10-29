"""Billing rules: issuing invoices, recording payments and the running account of an agreement."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import NumberSequence

from .models import Invoice, money

ZERO = Decimal("0")


class BillingError(Exception):
    pass


@transaction.atomic
def save_invoice(invoice, lines, user):
    if invoice.pk and not invoice.is_draft:
        raise BillingError(_("Only draft invoices can be changed."))
    if not invoice.pk:
        invoice.created_by = user
    invoice.save()
    invoice.lines.all().delete()
    for order, line in enumerate(lines):
        line.pk = None
        line.invoice = invoice
        line.order = order
        line.save()
    return invoice


@transaction.atomic
def issue_invoice(invoice):
    if not invoice.is_draft:
        raise BillingError(_("This invoice is already issued."))
    if not invoice.lines.exists():
        raise BillingError(_("Add at least one line before issuing."))
    invoice.number = NumberSequence.next_number("invoice", invoice.date)
    invoice.status = Invoice.Status.ISSUED
    invoice.issued_at = timezone.now()
    invoice.save(update_fields=["number", "status", "issued_at"])
    return invoice


@transaction.atomic
def cancel_invoice(invoice):
    if invoice.payments.exists():
        raise BillingError(_("Payments are recorded against this invoice; remove them before cancelling."))
    if invoice.is_draft:
        invoice.delete()
        return None
    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status"])
    return invoice


@transaction.atomic
def record_payment(invoice, payment, company, user):
    invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status != Invoice.Status.ISSUED:
        raise BillingError(_("Payments can only be recorded against issued invoices."))
    balance = invoice.amounts(company)["balance"]
    if payment.amount > balance:
        raise BillingError(_("Amount is more than the balance due (%(b)s).") % {"b": balance})
    payment.invoice = invoice
    payment.received_by = user
    payment.save()
    return payment


def billed_for_milestone(milestone, exclude=None):
    qs = milestone.invoices.exclude(status=Invoice.Status.CANCELLED)
    if exclude is not None and exclude.pk:
        qs = qs.exclude(pk=exclude.pk)
    total = ZERO
    for inv in qs.prefetch_related("lines"):
        total += sum((l.amount for l in inv.lines.all()), ZERO)
    return money(total)


def agreement_statement(agreement, company):
    """Contract value vs billed vs received, per milestone and in total."""
    invoices = list(agreement.invoices.exclude(status=Invoice.Status.CANCELLED)
                    .prefetch_related("lines", "payments").select_related("milestone"))
    amounts = {inv.pk: inv.amounts(company) for inv in invoices}
    rows = []
    for m in agreement.milestones.all():
        mine = [inv for inv in invoices if inv.milestone_id == m.pk]
        billed = sum((amounts[i.pk]["subtotal"] for i in mine), ZERO)
        received = sum((amounts[i.pk]["paid"] for i in mine), ZERO)
        rows.append({"milestone": m, "amount": m.amount, "billed": billed, "received": received,
                     "to_bill": max(m.amount - billed, ZERO), "invoices": mine})
    extra = [{"invoice": inv, "billed": amounts[inv.pk]["subtotal"], "received": amounts[inv.pk]["paid"]}
             for inv in invoices if inv.milestone_id is None]
    issued = [inv for inv in invoices if inv.status == Invoice.Status.ISSUED]
    totals = {
        "contract": agreement.contract_value,
        "billed": sum((amounts[i.pk]["subtotal"] for i in invoices), ZERO),
        "billed_issued": sum((amounts[i.pk]["subtotal"] for i in issued), ZERO),
        "tax": sum((amounts[i.pk]["tax"] for i in issued), ZERO),
        "retention": sum((amounts[i.pk]["retention"] for i in issued), ZERO),
        "received": sum((amounts[i.pk]["paid"] for i in invoices), ZERO),
        "outstanding": sum((amounts[i.pk]["balance"] for i in issued), ZERO),
    }
    totals["to_bill"] = max(agreement.contract_value - totals["billed"], ZERO)
    return {"rows": rows, "extra": extra, "totals": totals}


def receivables(company, today=None):
    """Unpaid issued invoices with their balance – for the dashboard and the receivables list."""
    today = today or timezone.localdate()
    result = []
    for inv in (Invoice.objects.filter(status=Invoice.Status.ISSUED)
                .select_related("client", "project").prefetch_related("lines", "payments")):
        a = inv.amounts(company)
        if a["balance"] > 0:
            result.append({"invoice": inv, "balance": a["balance"],
                           "overdue": bool(inv.due_date and inv.due_date < today)})
    return result


def payments_total(qs):
    return qs.aggregate(s=Sum("amount"))["s"] or ZERO

