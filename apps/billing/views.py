from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.numbers import format_money
from apps.core.pdf import pdf_response
from apps.documents.models import Agreement, PaymentMilestone
from apps.documents.rendering import plain_number

from .forms import InvoiceForm, InvoiceLineFormSet, PaymentForm
from .models import ClientPayment, Invoice
from .services import (BillingError, agreement_statement, billed_for_milestone, cancel_invoice, issue_invoice,
                       receivables, record_payment, save_invoice)



def state_label(state):
    labels = {"draft": _("Draft"), "issued": _("Issued"), "cancelled": _("Cancelled"), "paid": _("Paid"),
              "overdue": _("Overdue"), "partly_paid": _("Partly paid"), "unpaid": _("Unpaid")}
    return labels.get(state, state)


def _lines(formset):
    lines = []
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None) or {}
        if data.get("DELETE") or not data.get("description") or data.get("rate") in (None, ""):
            continue
        lines.append(form.save(commit=False))
    return lines


@login_required
@permission_required("billing.view_invoice", raise_exception=True)
def invoice_list(request):
    company = request.company
    qs = Invoice.objects.select_related("client", "project").prefetch_related("lines", "payments")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q) | Q(title__icontains=q))
    wanted = request.GET.get("state", "")
    rows = []
    for inv in qs:
        state = inv.payment_state(company)
        if wanted and state != wanted and not (wanted == "unpaid_all" and state in ("unpaid", "partly_paid", "overdue")):
            continue
        rows.append({"invoice": inv, "state": state, "label": state_label(state), "amounts": inv.amounts(company)})
    page = Paginator(rows, 30).get_page(request.GET.get("page"))
    outstanding = sum(r["balance"] for r in receivables(company))
    return render(request, "billing/invoice_list.html", {
        "page_obj": page, "outstanding": outstanding,
        "states": [("unpaid_all", _("Not fully paid")), ("overdue", _("Overdue")), ("paid", _("Paid")),
                   ("draft", _("Draft")), ("cancelled", _("Cancelled"))],
    })


def _invoice_form(request, invoice=None):
    company = request.company
    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            lines = _lines(formset)
            if not lines:
                form.add_error(None, _("Add at least one line."))
            else:
                try:
                    obj = save_invoice(form.save(commit=False), lines, request.user)
                    messages.success(request, _("Invoice saved as draft. Check it, then press Issue."))
                    return redirect("billing:invoice_detail", pk=obj.pk)
                except BillingError as exc:
                    form.add_error(None, str(exc))
    else:
        today = timezone.localdate()
        initial = {"date": today, "due_date": today + timedelta(days=company.invoice_due_days),
                   "terms": company.invoice_terms}
        lines = None
        if invoice:
            initial = None
            lines = [{"description": l.description, "tax_code": l.tax_code, "quantity": l.quantity, "unit": l.unit,
                      "rate": l.rate, "tax_rate": l.tax_rate} for l in invoice.lines.all()]
        elif request.GET.get("milestone"):
            m = get_object_or_404(PaymentMilestone.objects.select_related("agreement__client", "agreement__project"),
                                  pk=request.GET["milestone"])
            a = m.agreement
            count = a.invoices.exclude(status=Invoice.Status.CANCELLED).count() + 1
            remaining = max(m.amount - billed_for_milestone(m), 0)
            initial.update({"client": a.client, "project": a.project, "agreement": a, "milestone": m,
                            "retention_percent": a.retention_percent,
                            "title": _("Running bill %(n)s – %(m)s") % {"n": count, "m": m.description}})
            tax = company.default_tax_rate if company.tax_enabled else 0
            lines = [{"description": _("%(m)s (%(p)s%% of contract value %(v)s)") % {
                "m": m.description, "p": plain_number(m.percent), "v": format_money(a.contract_value)},
                "quantity": 1, "unit": "LS", "rate": remaining, "tax_rate": tax}]
        elif request.GET.get("agreement"):
            a = get_object_or_404(Agreement, pk=request.GET["agreement"])
            initial.update({"client": a.client, "project": a.project, "agreement": a,
                            "retention_percent": a.retention_percent, "title": _("Extra work")})
        form = InvoiceForm(instance=invoice, initial=initial)
        formset = InvoiceLineFormSet(prefix="lines", initial=lines)
    return render(request, "billing/invoice_form.html", {
        "form": form, "formset": formset, "invoice": invoice,
        "title": _("Edit draft invoice") if invoice else _("New invoice"),
    })


@login_required
@permission_required("billing.add_invoice", raise_exception=True)
def invoice_create(request):
    return _invoice_form(request)


@login_required
@permission_required("billing.change_invoice", raise_exception=True)
def invoice_update(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not invoice.is_draft:
        messages.error(request, _("Only draft invoices can be changed."))
        return redirect("billing:invoice_detail", pk=pk)
    return _invoice_form(request, invoice)


@login_required
@permission_required("billing.view_invoice", raise_exception=True)
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client", "project", "agreement", "milestone"), pk=pk)
    company = request.company
    form = PaymentForm(initial={"amount": invoice.amounts(company)["balance"]})
    state = invoice.payment_state(company)
    return render(request, "billing/invoice_detail.html", {
        "invoice": invoice, "lines": invoice.lines.all(), "a": invoice.amounts(company), "state": state,
        "state_label": state_label(state), "payments": invoice.payments.select_related("received_by"),
        "payment_form": form,
    })


@require_POST
@login_required
def invoice_action(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    action = request.POST.get("action")
    perm = {"issue": "billing.change_invoice", "cancel": "billing.delete_invoice"}.get(action)
    if not perm or not request.user.has_perm(perm):
        messages.error(request, _("Your role cannot do this."))
        return redirect("billing:invoice_detail", pk=pk)
    try:
        if action == "issue":
            issue_invoice(invoice)
            messages.success(request, _("Invoice %(n)s issued.") % {"n": invoice.number})
        else:
            if cancel_invoice(invoice) is None:
                messages.success(request, _("Draft deleted."))
                return redirect("billing:invoice_list")
            messages.success(request, _("Invoice cancelled."))
    except BillingError as exc:
        messages.error(request, str(exc))
    return redirect("billing:invoice_detail", pk=pk)


@require_POST
@login_required
@permission_required("billing.add_clientpayment", raise_exception=True)
def payment_add(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    form = PaymentForm(request.POST)
    if form.is_valid():
        try:
            record_payment(invoice, form.save(commit=False), request.company, request.user)
            messages.success(request, _("Payment recorded."))
        except BillingError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, _("Check the payment details: ") + "; ".join(
            f"{form.fields[f].label}: {' '.join(e)}" if f in form.fields else " ".join(e)
            for f, e in form.errors.items()))
    return redirect("billing:invoice_detail", pk=pk)


@require_POST
@login_required
@permission_required("billing.delete_clientpayment", raise_exception=True)
def payment_delete(request, pk):
    payment = get_object_or_404(ClientPayment, pk=pk)
    invoice_pk = payment.invoice_id
    payment.delete()
    messages.success(request, _("Payment removed."))
    return redirect("billing:invoice_detail", pk=invoice_pk)


@login_required
@permission_required("billing.view_invoice", raise_exception=True)
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client", "project", "agreement"), pk=pk)
    return pdf_response(request, "billing/invoice_pdf.html", {
        "invoice": invoice, "lines": invoice.lines.all(), "a": invoice.amounts(request.company),
    }, invoice.number or f"Draft-{invoice.pk}")


@login_required
@permission_required("billing.view_clientpayment", raise_exception=True)
def payment_list(request):
    qs = ClientPayment.objects.select_related("invoice__client")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(invoice__number__icontains=q) | Q(invoice__client__name__icontains=q) |
                       Q(reference__icontains=q))
    return render(request, "billing/payment_list.html",
                  {"page_obj": Paginator(qs, 50).get_page(request.GET.get("page"))})


@login_required
@permission_required("billing.view_invoice", raise_exception=True)
def statement(request, agreement_pk):
    agreement = get_object_or_404(Agreement.objects.select_related("client", "project"), pk=agreement_pk)
    data = agreement_statement(agreement, request.company)
    if request.GET.get("format") == "pdf":
        return pdf_response(request, "billing/statement_pdf.html", {"agreement": agreement, **data},
                            f"Statement-{agreement.number}")
    return render(request, "billing/statement.html", {"agreement": agreement, **data})
