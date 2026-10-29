"""
Stock posting rules. Every document that moves stock goes through here so the
ledger (StockMovement) and purchase-order progress always agree.
"""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import CompanySettings, NumberSequence

from .models import (GoodsReceipt, Material, MaterialIssue, PurchaseOrder, StockAdjustment, StockMovement,
                     StockTransfer)

ZERO = Decimal("0")


class StockError(Exception):
    pass


def plain(value):
    """100.000 → '100' (never scientific notation like 1E+2)."""
    return format(value.normalize(), "f")


def current_rates(lines):
    """Latest purchase rates from the database (line.material may be an older copy)."""
    ids = {line.material_id for line in lines}
    return dict(Material.objects.filter(pk__in=ids).values_list("pk", "last_purchase_rate"))


def balance(material, location):
    return (StockMovement.objects.filter(material=material, location=location)
            .aggregate(q=Sum("quantity"))["q"] or ZERO)


def balances(location=None, material=None, category=None, search=None):
    """Current stock per material (and per location when no location is given)."""
    qs = StockMovement.objects.all()
    if location:
        qs = qs.filter(location=location)
    if material:
        qs = qs.filter(material=material)
    if category:
        qs = qs.filter(material__category=category)
    if search:
        qs = qs.filter(material__name__icontains=search)
    group = ["material", "material__name", "material__code", "material__unit__symbol",
             "material__reorder_level", "material__last_purchase_rate"]
    if location is None:
        group += ["location", "location__name"]
    rows = qs.values(*group).annotate(qty=Sum("quantity")).order_by("material__name", *(
        ["location__name"] if location is None else []))
    result = []
    for row in rows:
        row["value"] = (row["qty"] * row["material__last_purchase_rate"]).quantize(Decimal("0.01"))
        result.append(row)
    return result


def low_stock():
    """Active materials whose total stock across all locations is at or below the reorder level."""
    totals = dict(StockMovement.objects.values_list("material").annotate(q=Sum("quantity")))
    items = []
    for m in Material.objects.filter(is_active=True, reorder_level__gt=0).select_related("unit"):
        qty = totals.get(m.pk, ZERO)
        if qty <= m.reorder_level:
            items.append({"material": m, "qty": qty})
    return items


def _check_available(location, needs):
    """needs: {material: qty taken out}. Raise if stock would go below zero."""
    if CompanySettings.load().allow_negative_stock:
        return
    short = []
    for material, qty in needs.items():
        have = balance(material, location)
        if have - qty < 0:
            short.append(_("%(m)s: only %(have)s %(unit)s at %(loc)s, need %(need)s") % {
                "m": material.name, "have": plain(have), "unit": material.unit.symbol,
                "loc": location.name, "need": plain(qty)})
    if short:
        raise StockError(_("Not enough stock. ") + "; ".join(short))


def _move(doc, kind, material, location, qty, rate):
    StockMovement.objects.create(
        date=doc.date, material=material, location=location, quantity=qty, rate=rate, kind=kind,
        doc_type=doc._meta.model_name, doc_id=doc.pk, doc_number=doc.number,
    )


def _number(doc, key):
    if not doc.number:
        doc.number = NumberSequence.next_number(key, doc.date)


# --- Purchase orders -------------------------------------------------------

@transaction.atomic
def save_purchase_order(po, lines, user):
    if po.pk and not po.is_draft:
        raise StockError(_("Only draft purchase orders can be changed."))
    _number(po, "purchase_order")
    if not po.pk:
        po.created_by = user
    po.save()
    po.lines.all().delete()
    for line in lines:
        line.order = po
        line.pk = None
        line.save()
    return po


@transaction.atomic
def approve_purchase_order(po, user):
    if not po.is_draft:
        raise StockError(_("This purchase order is not waiting for approval."))
    if not po.lines.exists():
        raise StockError(_("Add at least one material before approving."))
    po.status = PurchaseOrder.Status.APPROVED
    po.approved_by = user
    po.approved_at = timezone.now()
    po.save(update_fields=["status", "approved_by", "approved_at"])


@transaction.atomic
def cancel_purchase_order(po):
    if po.receipts.exists():
        raise StockError(_("Goods have already been received against this PO; it cannot be cancelled."))
    po.status = PurchaseOrder.Status.CANCELLED
    po.save(update_fields=["status"])


# --- Goods receipt ---------------------------------------------------------

@transaction.atomic
def post_goods_receipt(grn, lines, user):
    po = grn.purchase_order
    if po and not po.can_receive:
        raise StockError(_("This purchase order is not approved or is already closed."))
    per_line = defaultdict(lambda: ZERO)
    for line in lines:
        if line.quantity <= 0:
            raise StockError(_("Quantities must be more than zero."))
        if line.order_line_id:
            if not po or line.order_line.order_id != po.pk:
                raise StockError(_("Line does not belong to this purchase order."))
            per_line[line.order_line_id] += line.quantity
    if po:
        for ol in po.lines.select_for_update():
            if per_line[ol.pk] > ol.pending_quantity:
                raise StockError(_("%(m)s: receiving %(q)s but only %(p)s is pending on the PO.") % {
                    "m": ol.material.name, "q": plain(per_line[ol.pk]), "p": plain(ol.pending_quantity)})

    _number(grn, "goods_receipt")
    grn.created_by = user
    grn.save()
    for line in lines:
        line.receipt = grn
        line.save()
        _move(grn, StockMovement.Kind.RECEIPT, line.material, grn.location, line.quantity, line.rate)
        if line.rate:
            Material.objects.filter(pk=line.material_id).update(last_purchase_rate=line.rate)
    if po:
        for ol in po.lines.all():
            if per_line[ol.pk]:
                ol.received_quantity += per_line[ol.pk]
                ol.save(update_fields=["received_quantity"])
        po.refresh_status()
    return grn


# --- Transfers, issues, adjustments ----------------------------------------

def _totals(lines):
    needs = defaultdict(lambda: ZERO)
    for line in lines:
        needs[line.material] += line.quantity
    return needs


@transaction.atomic
def post_transfer(transfer, lines, user):
    if transfer.from_location_id == transfer.to_location_id:
        raise StockError(_("'From' and 'To' must be different locations."))
    if any(line.quantity <= 0 for line in lines):
        raise StockError(_("Quantities must be more than zero."))
    _check_available(transfer.from_location, _totals(lines))
    _number(transfer, "stock_transfer")
    transfer.created_by = user
    transfer.save()
    rates = current_rates(lines)
    for line in lines:
        line.transfer = transfer
        line.save()
        rate = rates[line.material_id]
        _move(transfer, StockMovement.Kind.TRANSFER_OUT, line.material, transfer.from_location, -line.quantity, rate)
        _move(transfer, StockMovement.Kind.TRANSFER_IN, line.material, transfer.to_location, line.quantity, rate)
    return transfer


@transaction.atomic
def post_issue(issue, lines, user):
    if any(line.quantity <= 0 for line in lines):
        raise StockError(_("Quantities must be more than zero."))
    _check_available(issue.location, _totals(lines))
    _number(issue, "material_issue")
    issue.created_by = user
    issue.save()
    rates = current_rates(lines)
    for line in lines:
        line.issue = issue
        line.save()
        _move(issue, StockMovement.Kind.ISSUE, line.material, issue.location, -line.quantity,
              rates[line.material_id])
    return issue


@transaction.atomic
def post_adjustment(adj, lines, user):
    if any(line.quantity == 0 for line in lines):
        raise StockError(_("Quantities cannot be zero."))
    removals = defaultdict(lambda: ZERO)
    for line in lines:
        if line.quantity < 0:
            removals[line.material] += -line.quantity
    _check_available(adj.location, removals)
    _number(adj, "stock_adjustment")
    adj.created_by = user
    adj.save()
    rates = current_rates(lines)
    for line in lines:
        line.adjustment = adj
        line.save()
        rate = line.rate or rates[line.material_id]
        if line.rate and line.quantity > 0 and not rates[line.material_id]:
            Material.objects.filter(pk=line.material_id).update(last_purchase_rate=line.rate)
            rates[line.material_id] = line.rate
        _move(adj, StockMovement.Kind.ADJUSTMENT, line.material, adj.location, line.quantity, rate)
    return adj


# --- Cancelling a posted document -----------------------------------------

@transaction.atomic
def delete_stock_document(doc):
    """Remove a posted document and its stock entries, if the stock is still there."""
    moves = list(StockMovement.objects.filter(doc_type=doc._meta.model_name, doc_id=doc.pk)
                 .select_related("material", "location", "material__unit"))
    # Removing an inflow takes stock away again – make sure it has not been used.
    by_location = defaultdict(lambda: defaultdict(lambda: ZERO))
    for m in moves:
        if m.quantity > 0:
            by_location[m.location][m.material] += m.quantity
    for location, needs in by_location.items():
        _check_available(location, needs)
    StockMovement.objects.filter(doc_type=doc._meta.model_name, doc_id=doc.pk).delete()
    if isinstance(doc, GoodsReceipt) and doc.purchase_order_id:
        for line in doc.lines.select_related("order_line"):
            if line.order_line_id:
                ol = line.order_line
                ol.received_quantity = max(ol.received_quantity - line.quantity, ZERO)
                ol.save(update_fields=["received_quantity"])
        po = doc.purchase_order
        doc.delete()
        po.refresh_status()
        return
    doc.delete()


DOCUMENT_TYPES = {
    "goodsreceipt": GoodsReceipt,
    "stocktransfer": StockTransfer,
    "materialissue": MaterialIssue,
    "stockadjustment": StockAdjustment,
}
