from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import unquote

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import CompanySettings
from apps.core.setup import ensure_defaults
from apps.documents.models import Client, Quotation, QuotationLine
from apps.sharing.models import SentMessage, ShareLink
from apps.sharing.services import decrypt_secret, encrypt_secret, whatsapp_number


class HelperTests(TestCase):
    def test_password_encryption_round_trip(self):
        stored = encrypt_secret("app-password-123")
        self.assertTrue(stored.startswith("enc:"))
        self.assertNotIn("app-password-123", stored)
        self.assertEqual(decrypt_secret(stored), "app-password-123")
        with override_settings(SECRET_KEY="another-key-entirely-different"):
            self.assertEqual(decrypt_secret(stored), "")

    def test_whatsapp_numbers(self):
        self.assertEqual(whatsapp_number("98410 55555", "91"), "919841055555")
        self.assertEqual(whatsapp_number("+91 98410-55555", "91"), "919841055555")
        self.assertEqual(whatsapp_number("098410 55555", "91"), "919841055555")
        self.assertEqual(whatsapp_number("0044 7700 900123", "91"), "447700900123")
        self.assertEqual(whatsapp_number("", "91"), "")


class SharingTests(TestCase):
    def setUp(self):
        ensure_defaults("india")
        self.company = CompanySettings.load()
        self.owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(self.owner)
        self.cust = Client.objects.create(name="Mr. Selvam", phone="98410 55555", email="selvam@example.com")
        self.quote = Quotation.objects.create(number="QT/2026-27/0007", date=date(2026, 10, 29), client=self.cust,
                                              subject="House")
        QuotationLine.objects.create(quotation=self.quote, description="Work", quantity=1, rate=Decimal("250000"))
        self.url = f"/send/quotation/{self.quote.pk}/"

    def setup_email(self):
        self.company.email_host = "smtp.example.com"
        self.company.email_username = "office@builder.example"
        self.company.email_password = encrypt_secret("secret")
        self.company.save()

    def test_share_page_prefills_from_client(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["email_form"].initial["to"], "selvam@example.com")
        self.assertIn("QT/2026-27/0007", page.context["email_form"].initial["subject"])
        self.assertIn("₹2,50,000.00", page.context["wa_form"].initial["text"])
        self.assertContains(page, "Email is not set up yet")

    def test_email_sends_pdf_attachment(self):
        self.setup_email()
        resp = self.client.post(self.url, {"action": "email", "email-to": "selvam@example.com, son@example.com",
                                           "email-cc": "", "email-subject": "Your quotation",
                                           "email-body": "Please see attached."})
        self.assertRedirects(resp, f"/documents/quotations/{self.quote.pk}/")
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["selvam@example.com", "son@example.com"])
        self.assertIn("office@builder.example", msg.from_email)
        from apps.core.pdf import HTML

        if HTML is not None:  # PDF engine installed: the PDF must be attached
            name, content, mime = msg.attachments[0]
            self.assertEqual(mime, "application/pdf")
            self.assertTrue(name.endswith(".pdf"))
            self.assertTrue(content.startswith(b"%PDF"))
        log = SentMessage.objects.get()
        self.assertEqual((log.channel, log.ok), ("email", True))

    def test_email_refused_without_server(self):
        resp = self.client.post(self.url, {"action": "email", "email-to": "a@b.com", "email-subject": "s",
                                           "email-body": "b"}, follow=True)
        self.assertContains(resp, "Email is not set up")
        self.assertEqual(len(mail.outbox), 0)

    def test_bad_email_address(self):
        self.setup_email()
        resp = self.client.post(self.url, {"action": "email", "email-to": "not-an-email", "email-subject": "s",
                                           "email-body": "b"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_whatsapp_creates_link_and_redirects(self):
        resp = self.client.post(self.url, {"action": "whatsapp", "wa-phone": "98410 55555",
                                           "wa-text": "Dear Selvam, quotation: (link is added when you press Send)"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("https://wa.me/919841055555?text="))
        link = ShareLink.objects.get()
        self.assertIn(f"/s/{link.token}/", unquote(resp["Location"]))
        self.assertNotIn("(link is added", unquote(resp["Location"]))

    def test_public_link_works_without_login_then_expires_or_stops(self):
        self.client.post(self.url, {"action": "link"})
        link = ShareLink.objects.get()
        self.client.logout()
        resp = self.client.get(f"/s/{link.token}/")
        self.assertEqual(resp.status_code, 200)
        link.refresh_from_db()
        self.assertEqual(link.view_count, 1)
        self.assertEqual(self.client.get("/s/not-a-real-token/").status_code, 410)

        self.client.force_login(self.owner)
        self.client.post(f"/send/link/{link.pk}/stop/")
        self.client.logout()
        self.assertEqual(self.client.get(f"/s/{link.token}/").status_code, 410)

        other = ShareLink.objects.create(doc_type="quotation", doc_id=self.quote.pk, label="x",
                                         expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(f"/s/{other.token}/").status_code, 410)

    def test_permissions(self):
        nobody = User.objects.create_user("nobody", password="x")
        self.client.force_login(nobody)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get("/send/bogus/1/").status_code, 404)

    def test_settings_keep_saved_password_when_left_blank(self):
        self.setup_email()
        form = self.client.get("/settings/").context["form"]
        data = {}
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if isinstance(value, bool):
                if value:
                    data[name] = "on"
            elif value is not None and name not in ("logo", "email_password"):
                data[name] = value
        self.client.post("/settings/", data)
        self.assertEqual(decrypt_secret(CompanySettings.load().email_password), "secret")
        data["email_password"] = "new-secret"
        self.client.post("/settings/", data)
        stored = CompanySettings.load().email_password
        self.assertTrue(stored.startswith("enc:"))
        self.assertEqual(decrypt_secret(stored), "new-secret")
