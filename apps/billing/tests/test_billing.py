from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import ClientPayment, Invoice, InvoiceLine
from apps.billing.services import (BillingError, agreement_statement, cancel_invoice, issue_invoice, receivables,
                                   record_payment, save_invoice)
from apps.core.models import CompanySettings, Project
from apps.core.numbers import amount_in_words
from apps.core.setup import ensure_defaults
from apps.documents.models import Agreement, Client, PaymentMilestone

D = Decimal


class BillingTestCase(TestCase):
    def setUp(self):
        ensure_defaults("india")
        self.company = CompanySettings.load()
        self.company.tax_enabled = True
        self.company.save()
        self.user = User.objects.create_superuser("owner", password="x")
        self.cust = Client.objects.create(name="Mr. Selvam", phone="98410 55555", email="selvam@example.com")
        self.project = Project.objects.create(name="Villa", code="V1", client=self.cust)
        self.agreement = Agreement.objects.create(number="AGR/1", date=date(2026, 10, 1), client=self.cust,
                                                  project=self.project, contract_value=D("1000000"),
                                                  retention_percent=D("5"))
        self.advance = PaymentMilestone.objects.create(agreement=self.agreement, order=1, description="Advance",
                                                       percent=D("10"))
        self.slab = PaymentMilestone.objects.create(agreement=self.agreement, order=2, description="Slab",
                                                    percent=D("30"))

    def make_invoice(self, milestone=None, rate="100000", tax="18", inter_state=False, retention="5"):
        inv = Invoice(date=date(2026, 10, 29), due_date=date(2026, 11, 13), client=self.cust, project=self.project,
                      agreement=self.agreement, milestone=milestone, title="Bill", inter_state=inter_state,
                      retention_percent=D(retention))
        return save_invoice(inv, [InvoiceLine(description="Work", quantity=1, rate=D(rate), tax_rate=D(tax))],
                            self.user)


class AmountsTests(BillingTestCase):
    def test_split_tax_and_retention(self):
        inv = self.make_invoice(self.advance)
        a = inv.amounts(self.company)
        self.assertEqual(a["subtotal"], D("100000.00"))
        self.assertEqual(a["tax"], D("18000.00"))
        self.assertEqual(a["tax_parts"], [("CGST", D("9000.00")), ("SGST", D("9000.00"))])
        self.assertEqual(a["retention"], D("5000.00"))
        self.assertEqual(a["payable"], D("113000.00"))

    def test_inter_state_uses_single_tax(self):
        inv = self.make_invoice(inter_state=True)
        self.assertEqual(inv.amounts(self.company)["tax_parts"], [("IGST", D("18000.00"))])

    def test_company_without_split(self):
        self.company.tax_split_enabled = False
        self.company.tax_label = "VAT"
        self.company.save()
        inv = self.make_invoice(tax="5")
        self.assertEqual(inv.amounts(self.company)["tax_parts"], [("VAT", D("5000.00"))])

    def test_odd_tax_split_adds_up(self):
        inv = self.make_invoice(rate="100.05", tax="18", retention="0")
        parts = inv.amounts(self.company)["tax_parts"]
        self.assertEqual(parts[0][1] + parts[1][1], inv.amounts(self.company)["tax"])

    def test_amount_in_words(self):
        self.assertEqual(amount_in_words(D("1234567.50"), self.company),
                         "Rupees Twelve Lakh Thirty-Four Thousand Five Hundred Sixty-Seven and Fifty Paise Only")
        self.company.number_grouping = "international"
        self.company.currency_name, self.company.currency_fraction_name = "Dirhams", "Fils"
        self.assertEqual(amount_in_words(D("1000000"), self.company), "Dirhams One Million Only")


class FlowTests(BillingTestCase):
    def test_number_only_given_on_issue(self):
        draft = self.make_invoice(self.advance)
        self.assertIsNone(draft.number)
        issue_invoice(draft)
        self.assertEqual(draft.number, "INV/2026-27/0001")
        with self.assertRaises(BillingError):
            save_invoice(draft, [], self.user)

    def test_deleting_a_draft_leaves_no_gap(self):
        cancel_invoice(self.make_invoice())  # draft deleted
        inv = self.make_invoice()
        issue_invoice(inv)
        self.assertEqual(inv.number, "INV/2026-27/0001")

    def test_payments_and_states(self):
        inv = issue_invoice(self.make_invoice(self.advance))
        today = date(2026, 11, 1)
        self.assertEqual(inv.payment_state(self.company, today), "unpaid")
        record_payment(inv, ClientPayment(amount=D("50000"), mode="upi"), self.company, self.user)
        self.assertEqual(inv.payment_state(self.company, today), "partly_paid")
        self.assertEqual(inv.payment_state(self.company, date(2026, 12, 1)), "overdue")
        with self.assertRaises(BillingError):
            record_payment(inv, ClientPayment(amount=D("63000.01")), self.company, self.user)
        record_payment(inv, ClientPayment(amount=D("63000")), self.company, self.user)
        self.assertEqual(inv.payment_state(self.company, date(2026, 12, 1)), "paid")
        with self.assertRaises(BillingError):
            cancel_invoice(inv)

    def test_no_payment_on_draft(self):
        with self.assertRaises(BillingError):
            record_payment(self.make_invoice(), ClientPayment(amount=D("1")), self.company, self.user)

    def test_statement(self):
        inv = issue_invoice(self.make_invoice(self.advance))
        record_payment(inv, ClientPayment(amount=D("113000")), self.company, self.user)
        issue_invoice(self.make_invoice(self.slab, rate="150000"))
        extra = issue_invoice(self.make_invoice(None, rate="20000"))
        cancelled = issue_invoice(self.make_invoice(self.slab, rate="999999"))
        cancel_invoice(cancelled)
        st = agreement_statement(self.agreement, self.company)
        adv, slab = st["rows"]
        self.assertEqual((adv["amount"], adv["billed"], adv["received"], adv["to_bill"]),
                         (D("100000.00"), D("100000.00"), D("113000.00"), D("0")))
        self.assertEqual((slab["billed"], slab["to_bill"]), (D("150000.00"), D("150000.00")))
        self.assertEqual([e["invoice"] for e in st["extra"]], [extra])
        self.assertEqual(st["totals"]["billed"], D("270000.00"))
        self.assertEqual(st["totals"]["retention"], D("13500.00"))
        self.assertEqual(st["totals"]["to_bill"], D("730000.00"))
        due = receivables(self.company, today=date(2026, 12, 1))
        self.assertEqual(len(due), 2)
        self.assertTrue(all(r["overdue"] for r in due))


class ScreenTests(BillingTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_raise_bill_from_milestone_issue_and_pay(self):
        page = self.client.get(f"/billing/new/?milestone={self.slab.pk}")
        self.assertContains(page, "Slab (30% of contract value 10,00,000.00)")
        self.assertEqual(page.context["form"].initial["retention_percent"], D("5"))
        resp = self.client.post("/billing/new/", {
            "client": self.cust.pk, "project": self.project.pk, "agreement": self.agreement.pk,
            "milestone": self.slab.pk, "title": "Running bill 1", "date": "2026-10-29", "due_date": "2026-11-13",
            "retention_percent": "5", "terms": "", "notes": "",
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "1",
            "lines-0-description": "Slab", "lines-0-tax_code": "9954", "lines-0-quantity": "1", "lines-0-unit": "LS",
            "lines-0-rate": "300000", "lines-0-tax_rate": "18",
        })
        inv = Invoice.objects.get()
        self.assertRedirects(resp, f"/billing/{inv.pk}/")
        self.client.post(f"/billing/{inv.pk}/action/", {"action": "issue"})
        inv.refresh_from_db()
        self.assertTrue(inv.number.startswith("INV/"))
        self.client.post(f"/billing/{inv.pk}/payment/", {"date": "2026-11-01", "amount": "100000", "mode": "bank"})
        self.assertEqual(inv.payments.count(), 1)
        for url in ["/billing/", "/billing/?state=unpaid_all", f"/billing/{inv.pk}/", "/billing/payments/",
                    f"/billing/agreement/{self.agreement.pk}/", f"/projects/{self.project.pk}/", "/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for url in [f"/billing/{inv.pk}/pdf/", f"/billing/agreement/{self.agreement.pk}/?format=pdf"]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                if resp["Content-Type"] == "application/pdf":
                    self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_milestone_from_other_agreement_rejected(self):
        other = Agreement.objects.create(number="AGR/2", date=date(2026, 10, 1), client=self.cust,
                                         contract_value=D("10"))
        resp = self.client.post("/billing/new/", {
            "client": self.cust.pk, "agreement": other.pk, "milestone": self.slab.pk, "title": "x",
            "date": "2026-10-29", "retention_percent": "0",
            "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
            "lines-0-description": "a", "lines-0-quantity": "1", "lines-0-unit": "LS", "lines-0-rate": "1",
            "lines-0-tax_rate": "0",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Invoice.objects.exists())

    def test_accountant_role_can_bill_storekeeper_cannot(self):
        from django.contrib.auth.models import Group

        acc = User.objects.create_user("acc", password="x")
        acc.groups.add(Group.objects.get(name="Accountant"))
        store = User.objects.create_user("store", password="x")
        store.groups.add(Group.objects.get(name="Storekeeper"))
        self.client.force_login(acc)
        self.assertEqual(self.client.get("/billing/new/").status_code, 200)
        self.client.force_login(store)
        self.assertEqual(self.client.get("/billing/").status_code, 403)
