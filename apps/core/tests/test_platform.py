import tempfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.core.models import AuditLog, CompanySettings, NumberSequence, Project
from apps.employees.models import Employee


class NumberSequenceTests(TestCase):
    def test_financial_year_numbering_restarts_each_year(self):
        self.assertEqual(NumberSequence.next_number("quotation", date(2027, 3, 31)), "QT/2026-27/0001")
        self.assertEqual(NumberSequence.next_number("quotation", date(2027, 3, 31)), "QT/2026-27/0002")
        self.assertEqual(NumberSequence.next_number("quotation", date(2027, 4, 1)), "QT/2027-28/0001")

    def test_calendar_year_company(self):
        company = CompanySettings.load()
        company.financial_year_start_month = 1
        company.save()
        self.assertEqual(NumberSequence.next_number("agreement", date(2026, 10, 1)), "AGR/2026/0001")

    def test_custom_pattern(self):
        NumberSequence.ensure_defaults()
        seq = NumberSequence.objects.get(key="purchase_order")
        seq.pattern, seq.padding, seq.next_value = "DC-PO-{YY}{MM}-{SEQ}", 3, 41
        seq.save()
        # same period as stored? stored period is blank so it restarts at 1 for the new format
        self.assertEqual(NumberSequence.next_number("purchase_order", date(2026, 10, 5)), "DC-PO-2610-001")


class SetupWizardTests(TestCase):
    def test_fresh_install_goes_to_setup_and_creates_owner(self):
        self.assertRedirects(self.client.get("/accounts/login/"), "/setup/")
        resp = self.client.post("/setup/", {
            "company_name": "Dhaksha Constructions", "phone": "", "address": "", "preset": "india",
            "language": "ta", "owner_name": "Vel Murugan", "username": "vel",
            "password1": "S3cure-pass-2026", "password2": "S3cure-pass-2026",
        })
        self.assertRedirects(resp, "/settings/")
        owner = User.objects.get()
        self.assertTrue(owner.is_superuser)
        self.assertEqual(owner.preferred_language, "ta")
        company = CompanySettings.load()
        self.assertEqual(company.name, "Dhaksha Constructions")
        self.assertEqual(company.tax_label, "GST")
        self.assertTrue(NumberSequence.objects.exists())
        # wizard is closed once a user exists
        self.client.logout()
        self.assertRedirects(self.client.get("/setup/"), "/accounts/login/")
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)


class ModuleSwitchTests(TestCase):
    def test_switched_off_module_is_hidden(self):
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        self.assertEqual(self.client.get("/inventory/").status_code, 200)
        company = CompanySettings.load()
        company.module_inventory = False
        company.save()
        self.assertEqual(self.client.get("/inventory/").status_code, 404)
        self.assertNotContains(self.client.get("/"), "/inventory/po/")


class LoginLockoutTests(TestCase):
    def test_locked_after_too_many_wrong_passwords(self):
        User.objects.create_user("ravi", password="right-password-123")
        for _ in range(5):
            self.client.post("/accounts/login/", {"username": "ravi", "password": "wrong"})
        resp = self.client.post("/accounts/login/", {"username": "ravi", "password": "right-password-123"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "locked")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_clears_failures(self):
        User.objects.create_user("ravi", password="right-password-123")
        for _ in range(3):
            self.client.post("/accounts/login/", {"username": "ravi", "password": "wrong"})
        resp = self.client.post("/accounts/login/", {"username": "ravi", "password": "right-password-123"})
        self.assertEqual(resp.status_code, 302)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProtectedMediaTests(TestCase):
    def test_id_proofs_only_for_allowed_roles(self):
        emp = Employee.objects.create(code="E1", name="E1")
        emp.id_proof_file.save("aadhaar.txt", SimpleUploadedFile("aadhaar.txt", b"secret"))
        url = emp.id_proof_file.url
        nobody = User.objects.create_user("nobody", password="x")
        self.client.force_login(nobody)
        self.assertEqual(self.client.get(url).status_code, 404)
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)


class AuditLogTests(TestCase):
    def test_changes_are_recorded_with_user(self):
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        project = Project.objects.create(name="Villa", code="V1")
        self.client.post(f"/projects/{project.pk}/edit/", {
            "name": "Villa", "code": "V1", "status": "on_hold", "geofence_radius_m": "200", "contract_value": "10",
        })
        entry = AuditLog.objects.filter(action="update", object_id=str(project.pk)).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.user, owner)
        self.assertEqual(entry.changes["status"], ["active", "on_hold"])
        self.assertEqual(self.client.get("/audit/").status_code, 200)


class ConfigurationPagesTests(TestCase):
    def test_pages(self):
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        NumberSequence.ensure_defaults()
        seq = NumberSequence.objects.first()
        for url in ["/configuration/", "/configuration/numbering/", f"/configuration/numbering/{seq.pk}/",
                    "/configuration/units/", "/configuration/units/new/", "/settings/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_settings_save(self):
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        form = self.client.get("/settings/").context["form"]
        data = {}
        for name, field in form.fields.items():
            value = form.initial.get(name, field.initial)
            if isinstance(value, bool):
                if value:
                    data[name] = "on"
            elif value is not None and name != "logo":
                data[name] = value
        data["name"] = "New Name Builders"
        data["brand_color"] = "#0055aa"
        resp = self.client.post("/settings/", data)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context", None) and resp.context["form"].errors)
        self.assertEqual(CompanySettings.load().name, "New Name Builders")
        self.assertContains(self.client.get("/"), "#0055aa")


class DemoDataTests(TestCase):
    def test_load_demo_then_every_main_page_renders(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from io import StringIO

        call_command("load_demo", stdout=StringIO())
        self.client.force_login(User.objects.get(username="owner"))
        project = Project.objects.get(code="SR01")
        for url in ["/", f"/projects/{project.pk}/", "/inventory/", "/inventory/po/", "/progress/",
                    "/documents/quotations/", "/documents/agreements/1/", "/attendance/register/", "/menu/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        with self.assertRaises(CommandError):
            call_command("load_demo", stdout=StringIO())

    def test_tamil_pages(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("load_demo", stdout=StringIO())
        owner = User.objects.get(username="owner")
        owner.preferred_language = "ta"
        owner.save()
        self.client.force_login(owner)
        self.assertContains(self.client.get("/inventory/po/"), "கொள்முதல் ஆணைகள்")
        self.assertContains(self.client.get("/configuration/"), "அமைப்புகள்")


class MoneyFormatTests(TestCase):
    def test_grouping_styles(self):
        from decimal import Decimal

        from apps.core.numbers import format_money

        self.assertEqual(format_money(Decimal("2246885.2"), style="indian"), "22,46,885.20")
        self.assertEqual(format_money(Decimal("2246885.2"), style="international"), "2,246,885.20")
        self.assertEqual(format_money(Decimal("-1234.5"), 0, style="indian"), "-1,235")
        self.assertEqual(format_money(Decimal("999"), style="indian"), "999.00")
        self.assertEqual(format_money(None), "")

    def test_company_setting_used_in_pages(self):
        from apps.core.models import Project

        company = CompanySettings.load()
        company.number_grouping = "indian"
        company.save()
        User.objects.create_superuser("owner", password="x")
        self.client.force_login(User.objects.get())
        Project.objects.create(name="V", code="V", contract_value=4250000)
        self.assertContains(self.client.get("/projects/"), "42,50,000.00")
