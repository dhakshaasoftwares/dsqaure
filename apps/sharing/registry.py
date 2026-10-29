"""
Which documents can be sent, who they normally go to, and how their PDF is built.
Each entry knows its model, the permission needed to see it and how to make its PDF.
"""

from dataclasses import dataclass
from typing import Callable

from django.utils.translation import gettext_lazy as _


@dataclass
class DocType:
    key: str
    title: object
    model_path: str
    perm: str
    module: str
    pdf: Callable          # (obj, company) -> (template_name, context)
    number: Callable       # obj -> str
    recipient: Callable    # obj -> (name, email, phone)
    amount: Callable       # (obj, company) -> Decimal | None
    detail_url: Callable   # obj -> url

    @property
    def model(self):
        from django.apps import apps

        return apps.get_model(self.model_path)


def _client(c):
    return (c.name, c.email, c.phone) if c else ("", "", "")


def _quotation_pdf(q, company):
    return "documents/quotation_pdf.html", {"quote": q, "lines": q.lines.all(), "totals": q.totals(company.tax_enabled)}


def _agreement_pdf(a, company):
    from apps.documents.rendering import render_agreement

    return "documents/agreement_pdf.html", {"agreement": a, "body_html": render_agreement(a, company)}


def _invoice_pdf(i, company):
    return "billing/invoice_pdf.html", {"invoice": i, "lines": i.lines.all(), "a": i.amounts(company)}


def _po_pdf(po, company):
    return "inventory/po_pdf.html", {"po": po, "lines": po.lines.select_related("material__unit")}


def _progress_pdf(p, company):
    from apps.progress.services import overall_percent

    return "progress/report_pdf.html", {
        "project": p, "stages": p.stages.all(), "overall": overall_percent(p), "photos": p.photos.all()[:12],
        "updates": p.progress_updates.select_related("stage")[:10]}


def _url(name):
    def build(obj):
        from django.urls import reverse

        return reverse(name, args=[obj.pk])
    return build


DOC_TYPES = {
    d.key: d for d in [
        DocType("quotation", _("Quotation"), "documents.Quotation", "documents.view_quotation", "documents",
                _quotation_pdf, lambda q: q.number, lambda q: _client(q.client),
                lambda q, c: q.totals(c.tax_enabled)["total"], _url("documents:quotation_detail")),
        DocType("agreement", _("Agreement"), "documents.Agreement", "documents.view_agreement", "documents",
                _agreement_pdf, lambda a: a.number, lambda a: _client(a.client),
                lambda a, c: a.contract_value, _url("documents:agreement_detail")),
        DocType("invoice", _("Invoice"), "billing.Invoice", "billing.view_invoice", "billing",
                _invoice_pdf, lambda i: i.number or "", lambda i: _client(i.client),
                lambda i, c: i.amounts(c)["payable"], _url("billing:invoice_detail")),
        DocType("purchase_order", _("Purchase order"), "inventory.PurchaseOrder", "inventory.view_purchaseorder",
                "inventory", _po_pdf, lambda po: po.number,
                lambda po: (po.supplier.name, po.supplier.email, po.supplier.phone),
                lambda po, c: po.total, _url("inventory:po_detail")),
        DocType("progress_report", _("Progress report"), "core.Project", "progress.view_projectstage", "progress",
                _progress_pdf, lambda p: p.code,
                lambda p: _client(p.client) if p.client_id else (p.client_name, "", p.client_phone),
                lambda p, c: None, _url("progress:project")),
    ]
}
