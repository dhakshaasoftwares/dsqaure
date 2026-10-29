from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_POST

from apps.core.pdf import pdf_response

from . import forms as f
from .models import (GoodsReceipt, Location, Material, MaterialCategory, MaterialIssue, PurchaseOrder,
                     StockAdjustment, StockMovement, StockTransfer)
from .services import (StockError, approve_purchase_order, balances, cancel_purchase_order,
                       delete_stock_document, post_adjustment, post_goods_receipt, post_issue, post_transfer,
                       save_purchase_order)


def materials_json():
    return {
        m.pk: {"rate": str(m.last_purchase_rate), "tax": str(m.tax_rate), "unit": m.unit.symbol}
        for m in Material.objects.filter(is_active=True).select_related("unit")
    }


def require(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def paginate(request, qs, per_page=30):
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


# --- Stock documents (receipt, transfer, issue, adjustment) -----------------

DOCS = {
    "receipt": dict(model=GoodsReceipt, form=f.GoodsReceiptForm, line_form=f.GoodsReceiptLineForm,
                    post=post_goods_receipt, title=_lazy("Goods receipt"), title_plural=_lazy("Goods receipts"),
                    perm="inventory.%s_goodsreceipt",
                    columns=["supplier", "location", "supplier_invoice_no"]),
    "transfer": dict(model=StockTransfer, form=f.StockTransferForm, line_form=f.StockTransferLineForm,
                     post=post_transfer, title=_lazy("Stock transfer"), title_plural=_lazy("Stock transfers"),
                     perm="inventory.%s_stocktransfer", columns=["from_location", "to_location"]),
    "issue": dict(model=MaterialIssue, form=f.MaterialIssueForm, line_form=f.MaterialIssueLineForm,
                  post=post_issue, title=_lazy("Material issue"), title_plural=_lazy("Material issues"),
                  perm="inventory.%s_materialissue", columns=["location", "purpose", "issued_to"]),
    "adjustment": dict(model=StockAdjustment, form=f.StockAdjustmentForm, line_form=f.StockAdjustmentLineForm,
                       post=post_adjustment, title=_lazy("Stock adjustment"), title_plural=_lazy("Stock adjustments"),
                       perm="inventory.%s_stockadjustment", columns=["location", "reason"]),
}


def get_cfg(kind):
    if kind not in DOCS:
        raise Http404
    return DOCS[kind]


@login_required
def doc_list(request, kind):
    cfg = get_cfg(kind)
    require(request.user, cfg["perm"] % "view")
    qs = cfg["model"].objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(number__icontains=q)
    page = paginate(request, qs)
    rows = []
    for doc in page:
        cells = []
        for col in cfg["columns"]:
            display = getattr(doc, f"get_{col}_display", None)
            cells.append(display() if display else getattr(doc, col))
        rows.append((doc, cells))
    headers = [cfg["model"]._meta.get_field(c).verbose_name for c in cfg["columns"]]
    return render(request, "inventory/doc_list.html", {
        "kind": kind, "cfg": cfg, "page_obj": page, "rows": rows, "headers": headers,
        "can_add": request.user.has_perm(cfg["perm"] % "add"),
    })


@login_required
def doc_create(request, kind):
    cfg = get_cfg(kind)
    require(request.user, cfg["perm"] % "add")
    po = None
    line_kwargs = {}
    initial_header, initial_lines = {}, []
    if kind == "receipt":
        po_id = request.GET.get("po") or request.POST.get("po")
        if po_id:
            po = get_object_or_404(PurchaseOrder, pk=po_id)
            if not po.can_receive:
                messages.error(request, _("This purchase order is not approved or is already closed."))
                return redirect("inventory:po_detail", pk=po.pk)
            initial_header = {"supplier": po.supplier, "location": po.location}
            initial_lines = [{"material": ol.material, "quantity": ol.pending_quantity, "rate": ol.rate,
                              "order_line": ol} for ol in po.lines.all() if ol.pending_quantity > 0]
        line_kwargs = {"purchase_order": po}
    Formset = f.line_formset(cfg["line_form"], extra=0 if initial_lines else 3)

    if request.method == "POST":
        form = cfg["form"](request.POST)
        formset = Formset(request.POST, prefix="lines", form_kwargs=line_kwargs)
        if form.is_valid() and formset.is_valid():
            doc = form.save(commit=False)
            if po:
                doc.purchase_order = po
                doc.supplier = po.supplier
            lines = f.cleaned_lines(formset)
            if not lines:
                form.add_error(None, _("Add at least one material line."))
            else:
                try:
                    cfg["post"](doc, lines, request.user)
                    messages.success(request, _("%(doc)s saved.") % {"doc": doc.number})
                    return redirect("inventory:doc_detail", kind=kind, pk=doc.pk)
                except StockError as exc:
                    form.add_error(None, str(exc))
    else:
        form = cfg["form"](initial=initial_header)
        formset = Formset(prefix="lines", initial=initial_lines or None, form_kwargs=line_kwargs)
    return render(request, "inventory/doc_form.html", {
        "kind": kind, "cfg": cfg, "form": form, "formset": formset, "po": po,
        "materials_json": materials_json(), "title": _("New %(doc)s") % {"doc": cfg["title"]},
    })


@login_required
def doc_detail(request, kind, pk):
    cfg = get_cfg(kind)
    require(request.user, cfg["perm"] % "view")
    doc = get_object_or_404(cfg["model"], pk=pk)
    return render(request, "inventory/doc_detail.html", {
        "kind": kind, "cfg": cfg, "doc": doc, "lines": doc.lines.select_related("material__unit"),
        "can_delete": request.user.has_perm(cfg["perm"] % "delete"),
    })


@require_POST
@login_required
def doc_delete(request, kind, pk):
    cfg = get_cfg(kind)
    require(request.user, cfg["perm"] % "delete")
    doc = get_object_or_404(cfg["model"], pk=pk)
    number = doc.number
    try:
        delete_stock_document(doc)
    except StockError as exc:
        messages.error(request, _("Cannot delete: ") + str(exc))
        return redirect("inventory:doc_detail", kind=kind, pk=pk)
    messages.success(request, _("%(doc)s deleted and stock reversed.") % {"doc": number})
    return redirect("inventory:doc_list", kind=kind)


# --- Purchase orders --------------------------------------------------------

@login_required
@permission_required("inventory.view_purchaseorder", raise_exception=True)
def po_list(request):
    qs = PurchaseOrder.objects.select_related("supplier", "location").prefetch_related("lines")
    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(number__icontains=q) | qs.filter(supplier__name__icontains=q)
    return render(request, "inventory/po_list.html", {
        "page_obj": paginate(request, qs), "statuses": PurchaseOrder.Status.choices,
    })


def _po_form(request, po=None):
    Formset = f.line_formset(f.PurchaseOrderLineForm, extra=1 if po else 3)
    if request.method == "POST":
        form = f.PurchaseOrderForm(request.POST, instance=po)
        formset = Formset(request.POST, prefix="lines")
        if form.is_valid() and formset.is_valid():
            lines = f.cleaned_lines(formset)
            if not lines:
                form.add_error(None, _("Add at least one material line."))
            else:
                try:
                    order = save_purchase_order(form.save(commit=False), lines, request.user)
                    messages.success(request, _("%(doc)s saved.") % {"doc": order.number})
                    return redirect("inventory:po_detail", pk=order.pk)
                except StockError as exc:
                    form.add_error(None, str(exc))
    else:
        initial = None if po else {"terms": request.company.po_terms}
        form = f.PurchaseOrderForm(instance=po, initial=initial)
        lines = [{"material": l.material, "description": l.description, "quantity": l.quantity, "rate": l.rate,
                  "tax_rate": l.tax_rate} for l in po.lines.all()] if po else None
        formset = Formset(prefix="lines", initial=lines)
    return render(request, "inventory/doc_form.html", {
        "kind": "po", "form": form, "formset": formset, "materials_json": materials_json(),
        "title": _("Edit %(doc)s") % {"doc": po.number} if po else _("New purchase order"),
    })


@login_required
@permission_required("inventory.add_purchaseorder", raise_exception=True)
def po_create(request):
    return _po_form(request)


@login_required
@permission_required("inventory.change_purchaseorder", raise_exception=True)
def po_update(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if not po.is_draft:
        messages.error(request, _("Only draft purchase orders can be changed."))
        return redirect("inventory:po_detail", pk=pk)
    return _po_form(request, po)


@login_required
@permission_required("inventory.view_purchaseorder", raise_exception=True)
def po_detail(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.select_related("supplier", "location", "created_by",
                                                                 "approved_by"), pk=pk)
    return render(request, "inventory/po_detail.html", {
        "po": po, "lines": po.lines.select_related("material__unit"), "receipts": po.receipts.all(),
    })


@login_required
@permission_required("inventory.view_purchaseorder", raise_exception=True)
def po_pdf(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.select_related("supplier", "location"), pk=pk)
    return pdf_response(request, "inventory/po_pdf.html",
                        {"po": po, "lines": po.lines.select_related("material__unit")}, po.number)


@require_POST
@login_required
def po_action(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "approve":
            require(request.user, "inventory.approve_purchaseorder")
            approve_purchase_order(po, request.user)
            messages.success(request, _("Purchase order approved."))
        elif action == "cancel":
            require(request.user, "inventory.change_purchaseorder")
            cancel_purchase_order(po)
            messages.success(request, _("Purchase order cancelled."))
        elif action == "delete":
            require(request.user, "inventory.delete_purchaseorder")
            if not po.is_draft:
                raise StockError(_("Only draft purchase orders can be deleted."))
            po.delete()
            messages.success(request, _("Draft purchase order deleted."))
            return redirect("inventory:po_list")
    except StockError as exc:
        messages.error(request, str(exc))
    return redirect("inventory:po_detail", pk=pk)


# --- Stock reports ---------------------------------------------------------

@login_required
@permission_required("inventory.view_stockmovement", raise_exception=True)
def stock(request):
    location = Location.objects.filter(pk=request.GET.get("location") or None).first()
    category = MaterialCategory.objects.filter(pk=request.GET.get("category") or None).first()
    rows = [r for r in balances(location=location, category=category, search=request.GET.get("q", "").strip())
            if r["qty"] or request.GET.get("zero")]
    total_value = sum(r["value"] for r in rows)
    return render(request, "inventory/stock.html", {
        "rows": rows, "location": location, "category": category, "total_value": total_value,
        "locations": Location.objects.filter(is_active=True), "categories": MaterialCategory.objects.all(),
    })


@login_required
@permission_required("inventory.view_stockmovement", raise_exception=True)
def ledger(request):
    qs = StockMovement.objects.select_related("material__unit", "location")
    material = Material.objects.filter(pk=request.GET.get("material") or None).first()
    location = Location.objects.filter(pk=request.GET.get("location") or None).first()
    if material:
        qs = qs.filter(material=material)
    if location:
        qs = qs.filter(location=location)
    page = paginate(request, qs, 50)
    kinds = {cfg["model"]._meta.model_name: kind for kind, cfg in DOCS.items()}
    for move in page:
        move.doc_kind = kinds.get(move.doc_type)
    return render(request, "inventory/ledger.html", {
        "page_obj": page, "material": material, "location": location,
        "materials": Material.objects.all(), "locations": Location.objects.all(),
    })
