from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.core.models import CompanySettings, Project
from apps.core.setup import ensure_masters
from apps.documents.models import Agreement, Client, PaymentMilestone, Quotation, QuotationLine
from apps.documents.rendering import agreement_values, render_agreement, render_body

D = Decimal


class QuotationTotalsTests(TestCase):
    def setUp(self):
        self.client_rec = Client.objects.create(name="Mr. Selvam")
        self.quote = Quotation.objects.create(number="QT/1", date=date(2026, 10, 29), client=self.client_rec,
                                              subject="House", discount_percent=D("10"))
        QuotationLine.objects.create(quotation=self.quote, description="Brickwork", quantity=D("100"),
                                     rate=D("50"), tax_rate=D("18"))
        QuotationLine.objects.create(quotation=self.quote, description="Labour", quantity=D("1"),
                                     rate=D("5000"), tax_rate=D("0"))

    def test_discount_then_tax(self):
        t = self.quote.totals(tax_enabled=True)
        self.assertEqual(t["subtotal"], D("10000.00"))
        self.assertEqual(t["discount"], D("1000.00"))
        self.assertEqual(t["tax"], D("810.00"))  # 5000 * 0.9 * 18%
        self.assertEqual(t["total"], D("9810.00"))

    def test_tax_switched_off(self):
        self.assertEqual(self.quote.totals(tax_enabled=False)["total"], D("9000.00"))


class RenderingTests(TestCase):
    def test_placeholders_headings_and_escaping(self):
        html = render_body("# Title\n\nHello {client_name}\nline two\n\n## Pay\n{unknown}",
                           {"client_name": "<b>Ravi</b>"})
        self.assertIn("<h2>Title</h2>", html)
        self.assertIn("<h3>Pay</h3>", html)
        self.assertIn("Hello &lt;b&gt;Ravi&lt;/b&gt;<br>line two", html)
        self.assertIn("{unknown}", html)

    def test_user_html_is_escaped(self):
        html = render_body("<script>alert(1)</script>", {})
        self.assertNotIn("<script>", html)

    def test_payment_schedule_table(self):
        company = CompanySettings.load()
        client = Client.objects.create(name="Owner")
        a = Agreement.objects.create(number="AGR/1", date=date(2026, 10, 29), client=client,
                                     contract_value=D("1000000"), body="Schedule:\n\n{payment_schedule}")
        PaymentMilestone.objects.create(agreement=a, order=1, description="Advance", percent=D("20"))
        PaymentMilestone.objects.create(agreement=a, order=2, description="Slab", percent=D("12.50"))
        html = render_agreement(a, company)
        self.assertIn(">20%<", html)
        self.assertIn(">12.5%<", html)
        self.assertNotIn("E+", html)
        self.assertIn("<table class='schedule'>", html)
        self.assertIn("200,000.00", html)
        self.assertEqual(agreement_values(a, company)["client_name"], "Owner")


class DocumentScreensTests(TestCase):
    def setUp(self):
        ensure_masters()
        self.owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(self.owner)
        self.cust = Client.objects.create(name="Sri Homes", address="Chennai")
        self.project = Project.objects.create(name="Tambaram Apartments", code="TMB", client=self.cust)

    def post_quotation(self):
        return self.client.post("/documents/quotations/new/", {
            "client": self.cust.pk, "project": self.project.pk, "date": "2026-10-29", "valid_until": "",
            "subject": "G+3 apartment", "introduction": "", "discount_percent": "0", "terms": "Terms",
            "status": "draft", "notes": "",
            "lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0",
            "lines-0-item": "", "lines-0-description": "Foundation", "lines-0-unit": "LS",
            "lines-0-quantity": "1", "lines-0-rate": "500000", "lines-0-tax_rate": "0",
            "lines-1-item": "", "lines-1-description": "", "lines-1-unit": "", "lines-1-quantity": "",
            "lines-1-rate": "", "lines-1-tax_rate": "0",
        })

    def test_quotation_to_agreement_flow(self):
        resp = self.post_quotation()
        quote = Quotation.objects.get()
        self.assertRedirects(resp, f"/documents/quotations/{quote.pk}/")
        self.assertTrue(quote.number.startswith("QT/"))
        self.assertEqual(quote.lines.count(), 1)

        page = self.client.get(f"/documents/agreements/new/?quotation={quote.pk}")
        self.assertContains(page, "500000")
        resp = self.client.post("/documents/agreements/new/", {
            "quotation": quote.pk, "client": self.cust.pk, "project": self.project.pk,
            "template": page.context["form"].initial["template"].pk, "title": "Construction Agreement",
            "date": "2026-10-29", "contract_value": "500000", "start_date": "", "completion_date": "",
            "site_address": "", "status": "draft",
            "ms-TOTAL_FORMS": "2", "ms-INITIAL_FORMS": "0",
            "ms-0-description": "Advance", "ms-0-percent": "20",
            "ms-1-description": "Slab", "ms-1-percent": "30",
        })
        agreement = Agreement.objects.get()
        self.assertRedirects(resp, f"/documents/agreements/{agreement.pk}/")
        self.assertEqual(agreement.quotation, quote)
        self.assertIn("{client_name}", agreement.body)
        detail = self.client.get(f"/documents/agreements/{agreement.pk}/")
        self.assertContains(detail, "Sri Homes")
        self.assertContains(detail, "add up to 50%")

    def test_milestones_over_100_rejected(self):
        resp = self.client.post("/documents/agreements/new/", {
            "client": self.cust.pk, "title": "X", "date": "2026-10-29", "contract_value": "100",
            "status": "draft", "template": "",
            "ms-TOTAL_FORMS": "2", "ms-INITIAL_FORMS": "0",
            "ms-0-description": "A", "ms-0-percent": "60", "ms-1-description": "B", "ms-1-percent": "50",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Agreement.objects.exists())

    def test_pdfs_and_pages(self):
        self.post_quotation()
        quote = Quotation.objects.get()
        a = Agreement.objects.create(number="AGR/X", date=date(2026, 10, 29), client=self.cust,
                                     contract_value=D("100"), body="# Agreement\n\nவணக்கம் {client_name}")
        for url in ["/documents/quotations/", "/documents/quotations/new/", f"/documents/quotations/{quote.pk}/",
                    f"/documents/quotations/{quote.pk}/edit/", f"/documents/quotations/new/?copy={quote.pk}",
                    "/documents/agreements/", "/documents/agreements/new/", f"/documents/agreements/{a.pk}/",
                    f"/documents/agreements/{a.pk}/edit/", f"/documents/agreements/{a.pk}/text/",
                    "/documents/clients/", "/documents/rates/", "/documents/rates/new/", "/documents/templates/",
                    "/documents/templates/placeholders/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for url in [f"/documents/quotations/{quote.pk}/pdf/", f"/documents/agreements/{a.pk}/pdf/"]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                if resp["Content-Type"] == "application/pdf":
                    self.assertTrue(resp.content.startswith(b"%PDF"))
