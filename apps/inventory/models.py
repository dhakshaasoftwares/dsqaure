from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

ZERO = Decimal("0")
QTY = dict(max_digits=12, decimal_places=3)
MONEY = dict(max_digits=12, decimal_places=2)


class MaterialCategory(models.Model):
    name = models.CharField(_("name"), max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("material category")
        verbose_name_plural = _("material categories")

    def __str__(self):
        return self.name


class Material(models.Model):
    code = models.CharField(_("code"), max_length=30, unique=True)
    name = models.CharField(_("name"), max_length=150)
    category = models.ForeignKey(MaterialCategory, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name=_("category"))
    unit = models.ForeignKey("core.Unit", on_delete=models.PROTECT, verbose_name=_("unit"))
    tax_code = models.CharField(_("tax code (HSN etc.)"), max_length=20, blank=True)
    tax_rate = models.DecimalField(_("tax rate %"), max_digits=5, decimal_places=2, default=ZERO)
    reorder_level = models.DecimalField(_("reorder level"), default=ZERO, **QTY,
                                        help_text=_("Warn when total stock falls to this quantity"))
    last_purchase_rate = models.DecimalField(_("last purchase rate"), default=ZERO, **MONEY)
    is_active = models.BooleanField(_("active"), default=True)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("material")
        verbose_name_plural = _("materials")

    def __str__(self):
        return f"{self.name} ({self.unit.symbol})"


class Supplier(models.Model):
    name = models.CharField(_("name"), max_length=200)
    contact_person = models.CharField(_("contact person"), max_length=100, blank=True)
    phone = models.CharField(_("phone"), max_length=30, blank=True)
    email = models.EmailField(_("email"), blank=True)
    address = models.TextField(_("address"), blank=True)
    tax_number = models.CharField(_("tax registration number"), max_length=50, blank=True)
    payment_terms = models.CharField(_("payment terms"), max_length=100, blank=True)
    bank_details = models.TextField(_("bank details"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("supplier")
        verbose_name_plural = _("suppliers")

    def __str__(self):
        return self.name


class Location(models.Model):
    """Where stock is kept: a project site (created automatically) or a godown / store."""

    class Kind(models.TextChoices):
        SITE = "site", _("Project site")
        GODOWN = "godown", _("Godown / store")

    name = models.CharField(_("name"), max_length=200)
    kind = models.CharField(_("type"), max_length=10, choices=Kind.choices, default=Kind.GODOWN)
    project = models.OneToOneField("core.Project", on_delete=models.CASCADE, null=True, blank=True,
                                   related_name="stock_location", editable=False)
    address = models.TextField(_("address"), blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["kind", "name"]
        verbose_name = _("stock location")
        verbose_name_plural = _("stock locations")

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft – waiting approval")
        APPROVED = "approved", _("Approved")
        PARTIAL = "partial", _("Partly received")
        RECEIVED = "received", _("Fully received")
        CANCELLED = "cancelled", _("Cancelled")

    number = models.CharField(_("PO number"), max_length=40, unique=True, editable=False)
    date = models.DateField(_("date"))
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders",
                                 verbose_name=_("supplier"))
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                 verbose_name=_("deliver to"))
    expected_date = models.DateField(_("expected delivery"), null=True, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(_("notes"), blank=True)
    terms = models.TextField(_("terms"), blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("purchase order")
        verbose_name_plural = _("purchase orders")
        permissions = [("approve_purchaseorder", "Can approve purchase orders")]

    def __str__(self):
        return self.number

    @property
    def is_draft(self):
        return self.status == self.Status.DRAFT

    @property
    def can_receive(self):
        return self.status in (self.Status.APPROVED, self.Status.PARTIAL)

    @property
    def subtotal(self):
        return sum((line.amount for line in self.lines.all()), ZERO)

    @property
    def tax_total(self):
        return sum((line.tax_amount for line in self.lines.all()), ZERO)

    @property
    def total(self):
        return self.subtotal + self.tax_total

    def refresh_status(self):
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return
        lines = list(self.lines.all())
        if lines and all(line.received_quantity >= line.quantity for line in lines):
            self.status = self.Status.RECEIVED
        elif any(line.received_quantity > 0 for line in lines):
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.APPROVED
        self.save(update_fields=["status"])


class PurchaseOrderLine(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name=_("material"))
    description = models.CharField(_("description / specification"), max_length=200, blank=True)
    quantity = models.DecimalField(_("quantity"), **QTY)
    rate = models.DecimalField(_("rate"), **MONEY)
    tax_rate = models.DecimalField(_("tax %"), max_digits=5, decimal_places=2, default=ZERO)
    received_quantity = models.DecimalField(_("received"), default=ZERO, editable=False, **QTY)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return f"{self.material} × {self.quantity}"

    @property
    def amount(self):
        return (self.quantity * self.rate).quantize(Decimal("0.01"))

    @property
    def tax_amount(self):
        return (self.amount * self.tax_rate / 100).quantize(Decimal("0.01"))

    @property
    def pending_quantity(self):
        return max(self.quantity - self.received_quantity, ZERO)


class StockDocument(models.Model):
    """Common fields for documents that move stock."""

    number = models.CharField(_("number"), max_length=40, unique=True, editable=False)
    date = models.DateField(_("date"))
    notes = models.TextField(_("notes"), blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["-date", "-pk"]

    def __str__(self):
        return self.number


class GoodsReceipt(StockDocument):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="receipts",
                                 verbose_name=_("supplier"))
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="receipts", verbose_name=_("purchase order"))
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                 verbose_name=_("received at"))
    supplier_invoice_no = models.CharField(_("supplier invoice / DC no."), max_length=50, blank=True)
    vehicle_no = models.CharField(_("vehicle no."), max_length=30, blank=True)

    class Meta(StockDocument.Meta):
        verbose_name = _("goods receipt")
        verbose_name_plural = _("goods receipts")

    @property
    def total(self):
        return sum((line.amount for line in self.lines.all()), ZERO)


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name=_("material"))
    order_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="receipt_lines")
    quantity = models.DecimalField(_("quantity"), **QTY)
    rate = models.DecimalField(_("rate"), **MONEY)

    @property
    def amount(self):
        return (self.quantity * self.rate).quantize(Decimal("0.01"))


class StockTransfer(StockDocument):
    from_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                      verbose_name=_("from"))
    to_location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                    verbose_name=_("to"))
    vehicle_no = models.CharField(_("vehicle no."), max_length=30, blank=True)

    class Meta(StockDocument.Meta):
        verbose_name = _("stock transfer")
        verbose_name_plural = _("stock transfers")


class StockTransferLine(models.Model):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name=_("material"))
    quantity = models.DecimalField(_("quantity"), **QTY)


class MaterialIssue(StockDocument):
    """Material used up at a site (consumption)."""

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                 verbose_name=_("site / store"))
    issued_to = models.CharField(_("issued to"), max_length=100, blank=True)
    purpose = models.CharField(_("used for"), max_length=200, blank=True,
                               help_text=_("e.g. 2nd floor slab, compound wall"))

    class Meta(StockDocument.Meta):
        verbose_name = _("material issue")
        verbose_name_plural = _("material issues")


class MaterialIssueLine(models.Model):
    issue = models.ForeignKey(MaterialIssue, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name=_("material"))
    quantity = models.DecimalField(_("quantity"), **QTY)


class StockAdjustment(StockDocument):
    """Opening stock, physical count corrections, damage / theft."""

    class Reason(models.TextChoices):
        OPENING = "opening", _("Opening stock")
        COUNT = "count", _("Physical count correction")
        DAMAGE = "damage", _("Damaged / wasted")
        OTHER = "other", _("Other")

    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="+",
                                 verbose_name=_("site / store"))
    reason = models.CharField(_("reason"), max_length=10, choices=Reason.choices, default=Reason.OPENING)

    class Meta(StockDocument.Meta):
        verbose_name = _("stock adjustment")
        verbose_name_plural = _("stock adjustments")


class StockAdjustmentLine(models.Model):
    adjustment = models.ForeignKey(StockAdjustment, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, verbose_name=_("material"))
    quantity = models.DecimalField(_("quantity (+ add / − remove)"), **QTY)
    rate = models.DecimalField(_("rate"), default=ZERO, **MONEY)


class StockMovement(models.Model):
    """Stock ledger. Balance at a location = sum of quantity. Never edited directly."""

    class Kind(models.TextChoices):
        RECEIPT = "receipt", _("Received")
        TRANSFER_IN = "transfer_in", _("Transfer in")
        TRANSFER_OUT = "transfer_out", _("Transfer out")
        ISSUE = "issue", _("Used / issued")
        ADJUSTMENT = "adjustment", _("Adjustment")

    date = models.DateField(_("date"), db_index=True)
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="movements",
                                 verbose_name=_("material"))
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="movements",
                                 verbose_name=_("location"))
    quantity = models.DecimalField(_("quantity"), **QTY)
    rate = models.DecimalField(_("rate"), default=ZERO, **MONEY)
    kind = models.CharField(_("type"), max_length=15, choices=Kind.choices)
    doc_type = models.CharField(max_length=30)
    doc_id = models.PositiveIntegerField()
    doc_number = models.CharField(_("document"), max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        indexes = [models.Index(fields=["material", "location"]), models.Index(fields=["doc_type", "doc_id"])]
        verbose_name = _("stock movement")
        verbose_name_plural = _("stock movements")

    def __str__(self):
        return f"{self.date} {self.material} {self.quantity} @ {self.location}"
