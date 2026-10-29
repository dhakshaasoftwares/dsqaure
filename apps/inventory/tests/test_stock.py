from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.core.models import CompanySettings, Project, Unit
from apps.inventory.models import (GoodsReceiptLine, Location, Material, MaterialIssue, MaterialIssueLine,
                                   PurchaseOrder, PurchaseOrderLine, StockAdjustment, StockAdjustmentLine,
                                   StockTransfer, StockTransferLine, Supplier, GoodsReceipt)
from apps.inventory.services import (StockError, approve_purchase_order, balance, cancel_purchase_order,
                                     delete_stock_document, low_stock, post_adjustment, post_goods_receipt,
                                     post_issue, post_transfer, save_purchase_order)

D = Decimal
TODAY = date(2026, 10, 29)


class StockTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("store", password="x")
        bag = Unit.objects.create(name="Bag", symbol="Bag")
        self.cement = Material.objects.create(code="CEM", name="Cement", unit=bag, reorder_level=D("50"))
        self.supplier = Supplier.objects.create(name="Sri Cements")
        self.site = Project.objects.create(name="Villa", code="V1")
        self.site_loc = self.site.stock_location
        self.godown = Location.objects.create(name="Main godown")

    def make_po(self, qty="100", rate="400"):
        po = PurchaseOrder(date=TODAY, supplier=self.supplier, location=self.godown)
        save_purchase_order(po, [PurchaseOrderLine(material=self.cement, quantity=D(qty), rate=D(rate),
                                                   tax_rate=D("28"))], self.user)
        return po

    def receive(self, po, qty, rate="400"):
        line = po.lines.get()
        grn = GoodsReceipt(date=TODAY, supplier=self.supplier, location=po.location, purchase_order=po)
        return post_goods_receipt(grn, [GoodsReceiptLine(material=self.cement, order_line=line,
                                                         quantity=D(qty), rate=D(rate))], self.user)

    def opening(self, location, qty, rate="380"):
        adj = StockAdjustment(date=TODAY, location=location)
        return post_adjustment(adj, [StockAdjustmentLine(material=self.cement, quantity=D(qty), rate=D(rate))],
                               self.user)


class SiteLocationTests(StockTestCase):
    def test_project_gets_a_stock_location(self):
        self.assertEqual(self.site_loc.name, "Villa")
        self.assertEqual(self.site_loc.kind, Location.Kind.SITE)
        self.site.name = "Villa Phase 1"
        self.site.save()
        self.site_loc.refresh_from_db()
        self.assertEqual(self.site_loc.name, "Villa Phase 1")


class PurchaseFlowTests(StockTestCase):
    def test_numbering_and_totals(self):
        po = self.make_po()
        self.assertTrue(po.number.startswith("PO/2026-27/"))
        self.assertEqual(po.subtotal, D("40000.00"))
        self.assertEqual(po.tax_total, D("11200.00"))
        self.assertEqual(po.total, D("51200.00"))

    def test_cannot_receive_unapproved_po(self):
        po = self.make_po()
        with self.assertRaises(StockError):
            self.receive(po, "10")

    def test_partial_then_full_receipt(self):
        po = self.make_po()
        approve_purchase_order(po, self.user)
        self.receive(po, "60")
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.PARTIAL)
        self.assertEqual(balance(self.cement, self.godown), D("60"))
        self.receive(po, "40", rate="410")
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(balance(self.cement, self.godown), D("100"))
        self.cement.refresh_from_db()
        self.assertEqual(self.cement.last_purchase_rate, D("410"))

    def test_over_receipt_rejected(self):
        po = self.make_po()
        approve_purchase_order(po, self.user)
        with self.assertRaises(StockError):
            self.receive(po, "101")
        self.assertEqual(balance(self.cement, self.godown), D("0"))

    def test_approved_po_cannot_be_edited_and_received_po_cannot_be_cancelled(self):
        po = self.make_po()
        approve_purchase_order(po, self.user)
        with self.assertRaises(StockError):
            save_purchase_order(po, [], self.user)
        self.receive(po, "10")
        with self.assertRaises(StockError):
            cancel_purchase_order(po)

    def test_deleting_receipt_reverses_stock_and_po(self):
        po = self.make_po()
        approve_purchase_order(po, self.user)
        grn = self.receive(po, "100")
        delete_stock_document(grn)
        po.refresh_from_db()
        self.assertEqual(po.status, PurchaseOrder.Status.APPROVED)
        self.assertEqual(po.lines.get().received_quantity, D("0"))
        self.assertEqual(balance(self.cement, self.godown), D("0"))

    def test_cannot_delete_receipt_whose_stock_was_used(self):
        po = self.make_po()
        approve_purchase_order(po, self.user)
        grn = self.receive(po, "100")
        issue = MaterialIssue(date=TODAY, location=self.godown)
        post_issue(issue, [MaterialIssueLine(material=self.cement, quantity=D("30"))], self.user)
        with self.assertRaises(StockError):
            delete_stock_document(grn)


class MovementTests(StockTestCase):
    def test_transfer_moves_stock(self):
        self.opening(self.godown, "100")
        t = StockTransfer(date=TODAY, from_location=self.godown, to_location=self.site_loc)
        post_transfer(t, [StockTransferLine(material=self.cement, quantity=D("40"))], self.user)
        self.assertEqual(balance(self.cement, self.godown), D("60"))
        self.assertEqual(balance(self.cement, self.site_loc), D("40"))

    def test_transfer_more_than_available_rejected(self):
        self.opening(self.godown, "100")
        t = StockTransfer(date=TODAY, from_location=self.godown, to_location=self.site_loc)
        with self.assertRaises(StockError) as err:
            post_transfer(t, [StockTransferLine(material=self.cement, quantity=D("110"))], self.user)
        self.assertIn("only 100 Bag", str(err.exception))
        self.assertNotIn("E+", str(err.exception))
        self.assertFalse(StockTransfer.objects.exists())

    def test_same_material_on_two_lines_counts_together(self):
        self.opening(self.site_loc, "10")
        issue = MaterialIssue(date=TODAY, location=self.site_loc)
        with self.assertRaises(StockError):
            post_issue(issue, [MaterialIssueLine(material=self.cement, quantity=D("6")),
                               MaterialIssueLine(material=self.cement, quantity=D("6"))], self.user)

    def test_negative_stock_allowed_by_setting(self):
        company = CompanySettings.load()
        company.allow_negative_stock = True
        company.save()
        issue = MaterialIssue(date=TODAY, location=self.site_loc)
        post_issue(issue, [MaterialIssueLine(material=self.cement, quantity=D("5"))], self.user)
        self.assertEqual(balance(self.cement, self.site_loc), D("-5"))

    def test_issue_valued_at_last_purchase_rate(self):
        self.opening(self.site_loc, "20", rate="380")
        # self.cement is deliberately not refreshed: the rate must come from the database
        issue = MaterialIssue(date=TODAY, location=self.site_loc)
        post_issue(issue, [MaterialIssueLine(material=self.cement, quantity=D("5"))], self.user)
        move = self.cement.movements.get(kind="issue")
        self.assertEqual(move.rate, D("380"))
        self.assertEqual(move.quantity, D("-5"))

    def test_low_stock(self):
        self.opening(self.godown, "30")
        self.assertEqual([r["material"] for r in low_stock()], [self.cement])
        self.opening(self.site_loc, "30")
        self.assertEqual(low_stock(), [])


class InventoryViewTests(StockTestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(self.owner)

    def test_create_po_approve_and_receive_through_screens(self):
        resp = self.client.post("/inventory/po/new/", {
            "date": "2026-10-29", "supplier": self.supplier.pk, "location": self.godown.pk, "terms": "",
            "lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0",
            "lines-0-material": self.cement.pk, "lines-0-quantity": "50", "lines-0-rate": "400",
            "lines-0-tax_rate": "0", "lines-0-description": "",
            "lines-1-material": "", "lines-1-quantity": "", "lines-1-rate": "", "lines-1-tax_rate": "0",
        })
        po = PurchaseOrder.objects.get()
        self.assertRedirects(resp, f"/inventory/po/{po.pk}/")
        self.client.post(f"/inventory/po/{po.pk}/action/", {"action": "approve"})
        po.refresh_from_db()
        self.assertEqual(po.status, "approved")

        page = self.client.get(f"/inventory/receipt/new/?po={po.pk}")
        self.assertContains(page, 'name="lines-0-order_line"')
        line = po.lines.get()
        resp = self.client.post("/inventory/receipt/new/", {
            "po": po.pk, "date": "2026-10-29", "supplier": self.supplier.pk, "location": self.godown.pk,
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "1",
            "lines-0-material": self.cement.pk, "lines-0-quantity": "50", "lines-0-rate": "400",
            "lines-0-order_line": line.pk,
        })
        self.assertEqual(resp.status_code, 302)
        po.refresh_from_db()
        self.assertEqual(po.status, "received")
        self.assertEqual(balance(self.cement, self.godown), D("50"))

    def test_stock_error_shown_on_form(self):
        resp = self.client.post("/inventory/issue/new/", {
            "date": "2026-10-29", "location": self.site_loc.pk,
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
            "lines-0-material": self.cement.pk, "lines-0-quantity": "5",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Not enough stock")

    def test_pages_render(self):
        self.opening(self.godown, "10")
        po = self.make_po()
        adj = StockAdjustment.objects.get()
        for url in ["/inventory/", "/inventory/ledger/", "/inventory/po/", "/inventory/po/new/",
                    f"/inventory/po/{po.pk}/", f"/inventory/po/{po.pk}/edit/", f"/inventory/po/{po.pk}/pdf/",
                    "/inventory/receipt/list/", "/inventory/receipt/new/", "/inventory/transfer/list/",
                    "/inventory/transfer/new/", "/inventory/issue/new/", "/inventory/adjustment/list/",
                    f"/inventory/adjustment/{adj.pk}/", "/inventory/materials/", "/inventory/materials/new/",
                    f"/inventory/materials/{self.cement.pk}/", "/inventory/suppliers/", "/inventory/locations/",
                    "/inventory/categories/", f"/projects/{self.site.pk}/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_unknown_document_kind_is_404(self):
        self.assertEqual(self.client.get("/inventory/bogus/list/").status_code, 404)
        self.assertEqual(self.client.get("/inventory/materials/new/").status_code, 200)
