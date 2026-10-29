from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.models import NumberSequence
from apps.core.pdf import pdf_response

from .forms import AgreementForm, AgreementTextForm, MilestoneFormSet, QuotationForm, QuotationLineForm
from .models import Agreement, DocumentTemplate, PaymentMilestone, Quotation, QuotationLine, WorkItem
from .rendering import PLACEHOLDERS, render_agreement

QuotationLineFormSet = forms.formset_factory(QuotationLineForm, extra=3, can_delete=True)


def items_json():
    return {
        i.pk: {"name": i.name, "description": i.description, "unit": i.unit.symbol if i.unit else "",
               "rate": str(i.rate), "tax": str(i.tax_rate)}
        for i in WorkItem.objects.filter(is_active=True).select_related("unit")
    }


def _lines(formset):
    lines = []
    for order, form in enumerate(formset.forms):
        data = getattr(form, "cleaned_data", None) or {}
        if data.get("DELETE") or not data.get("quantity"):
            continue
        line = form.save(commit=False)
        line.order = order
        lines.append(line)
    return lines


# --- Quotations -----------------------------------------------------------

@login_required
@permission_required("documents.view_quotation", raise_exception=True)
def quotation_list(request):
    qs = Quotation.objects.select_related("client", "project").prefetch_related("lines")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q) | Q(subject__icontains=q))
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    tax = request.company.tax_enabled
    for quote in page:
        quote.total_amount = quote.totals(tax)["total"]
    return render(request, "documents/quotation_list.html",
                  {"page_obj": page, "statuses": Quotation.Status.choices})


def _quotation_form(request, quote=None, copy_from=None):
    if request.method == "POST":
        form = QuotationForm(request.POST, instance=quote)
        formset = QuotationLineFormSet(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            lines = _lines(formset)
            if not lines:
                form.add_error(None, _("Add at least one line."))
            else:
                with transaction.atomic():
                    obj = form.save(commit=False)
                    if not obj.number:
                        obj.number = NumberSequence.next_number("quotation", obj.date)
                        obj.created_by = request.user
                    obj.save()
                    obj.lines.all().delete()
                    for line in lines:
                        line.quotation = obj
                        line.save()
                messages.success(request, _("%(doc)s saved.") % {"doc": obj.number})
                return redirect("documents:quotation_detail", pk=obj.pk)
    else:
        company = request.company
        source = quote or copy_from
        if quote:
            form = QuotationForm(instance=quote)
        else:
            today = timezone.localdate()
            initial = {"date": today, "valid_until": today + timedelta(days=company.quotation_validity_days),
                       "terms": company.quotation_terms}
            if copy_from:
                initial.update({f: getattr(copy_from, f) for f in
                                ("client", "project", "subject", "introduction", "discount_percent", "terms")})
            elif request.GET.get("client"):
                initial["client"] = request.GET["client"]
            form = QuotationForm(initial=initial)
        initial_lines = [{"item": l.item, "description": l.description, "unit": l.unit, "quantity": l.quantity,
                          "rate": l.rate, "tax_rate": l.tax_rate} for l in source.lines.all()] if source else None
        formset = QuotationLineFormSet(prefix="lines", initial=initial_lines)
    return render(request, "documents/quotation_form.html", {
        "form": form, "formset": formset, "items_json": items_json(), "quote": quote,
        "title": _("Edit %(doc)s") % {"doc": quote.number} if quote else _("New quotation"),
    })


@login_required
@permission_required("documents.add_quotation", raise_exception=True)
def quotation_create(request):
    copy_from = None
    if request.GET.get("copy"):
        copy_from = get_object_or_404(Quotation, pk=request.GET["copy"])
    return _quotation_form(request, copy_from=copy_from)


@login_required
@permission_required("documents.change_quotation", raise_exception=True)
def quotation_update(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    return _quotation_form(request, quote)


@login_required
@permission_required("documents.view_quotation", raise_exception=True)
def quotation_detail(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("client", "project"), pk=pk)
    return render(request, "documents/quotation_detail.html", {
        "quote": quote, "lines": quote.lines.all(), "totals": quote.totals(request.company.tax_enabled),
        "statuses": Quotation.Status.choices,
    })


@require_POST
@login_required
@permission_required("documents.change_quotation", raise_exception=True)
def quotation_status(request, pk):
    quote = get_object_or_404(Quotation, pk=pk)
    status = request.POST.get("status")
    if status in Quotation.Status.values:
        quote.status = status
        quote.save(update_fields=["status"])
        messages.success(request, _("Status updated."))
    return redirect("documents:quotation_detail", pk=pk)


@login_required
@permission_required("documents.view_quotation", raise_exception=True)
def quotation_pdf(request, pk):
    quote = get_object_or_404(Quotation.objects.select_related("client", "project"), pk=pk)
    return pdf_response(request, "documents/quotation_pdf.html", {
        "quote": quote, "lines": quote.lines.all(), "totals": quote.totals(request.company.tax_enabled),
    }, quote.number)


# --- Agreements ------------------------------------------------------------

@login_required
@permission_required("documents.view_agreement", raise_exception=True)
def agreement_list(request):
    qs = Agreement.objects.select_related("client", "project")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(client__name__icontains=q) | Q(title__icontains=q))
    return render(request, "documents/agreement_list.html",
                  {"page_obj": Paginator(qs, 30).get_page(request.GET.get("page"))})


def _agreement_form(request, agreement=None):
    quote = None
    if request.method == "POST":
        quote = Quotation.objects.filter(pk=request.POST.get("quotation") or None).first()
        form = AgreementForm(request.POST, instance=agreement)
        formset = MilestoneFormSet(request.POST, prefix="ms")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                new = not obj.pk
                if new:
                    obj.number = NumberSequence.next_number("agreement", obj.date)
                    obj.created_by = request.user
                    obj.quotation = quote
                if new or request.POST.get("reload_template"):
                    template = obj.template or DocumentTemplate.objects.filter(is_active=True).first()
                    obj.body = template.body if template else ""
                obj.save()
                obj.milestones.all().delete()
                order = 0
                for f in formset.forms:
                    d = getattr(f, "cleaned_data", None) or {}
                    if d.get("DELETE") or not d.get("description"):
                        continue
                    order += 1
                    PaymentMilestone.objects.create(agreement=obj, order=order, description=d["description"],
                                                    percent=d.get("percent") or 0)
            messages.success(request, _("%(doc)s saved.") % {"doc": obj.number})
            return redirect("documents:agreement_detail", pk=obj.pk)
    else:
        initial = None
        if not agreement:
            initial = {"date": timezone.localdate()}
            if request.GET.get("quotation"):
                quote = get_object_or_404(Quotation, pk=request.GET["quotation"])
                initial.update({
                    "client": quote.client, "project": quote.project, "title": quote.subject,
                    "contract_value": quote.totals(request.company.tax_enabled)["total"],
                    "site_address": quote.project.address if quote.project else "",
                })
        form = AgreementForm(instance=agreement, initial=initial)
        ms = [{"description": m.description, "percent": m.percent} for m in agreement.milestones.all()] \
            if agreement else None
        formset = MilestoneFormSet(prefix="ms", initial=ms)
    return render(request, "documents/agreement_form.html", {
        "form": form, "formset": formset, "agreement": agreement, "quote": quote,
        "title": _("Edit %(doc)s") % {"doc": agreement.number} if agreement else _("New agreement"),
    })


@login_required
@permission_required("documents.add_agreement", raise_exception=True)
def agreement_create(request):
    return _agreement_form(request)


@login_required
@permission_required("documents.change_agreement", raise_exception=True)
def agreement_update(request, pk):
    return _agreement_form(request, get_object_or_404(Agreement, pk=pk))


@login_required
@permission_required("documents.change_agreement", raise_exception=True)
def agreement_text(request, pk):
    agreement = get_object_or_404(Agreement, pk=pk)
    form = AgreementTextForm(request.POST or None, instance=agreement)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Agreement text saved."))
        return redirect("documents:agreement_detail", pk=pk)
    return render(request, "documents/agreement_text.html",
                  {"agreement": agreement, "form": form, "placeholders": PLACEHOLDERS})


@login_required
@permission_required("documents.view_agreement", raise_exception=True)
def agreement_detail(request, pk):
    agreement = get_object_or_404(Agreement.objects.select_related("client", "project", "quotation"), pk=pk)
    total_pct = sum(m.percent for m in agreement.milestones.all())
    return render(request, "documents/agreement_detail.html", {
        "agreement": agreement, "body_html": render_agreement(agreement, request.company),
        "milestones": agreement.milestones.all(), "total_pct": total_pct,
    })


@login_required
@permission_required("documents.view_agreement", raise_exception=True)
def agreement_pdf(request, pk):
    agreement = get_object_or_404(Agreement.objects.select_related("client", "project"), pk=pk)
    return pdf_response(request, "documents/agreement_pdf.html", {
        "agreement": agreement, "body_html": render_agreement(agreement, request.company),
    }, agreement.number)


@login_required
@permission_required("documents.view_documenttemplate", raise_exception=True)
def placeholders(request):
    return render(request, "documents/placeholders.html", {"placeholders": PLACEHOLDERS})
