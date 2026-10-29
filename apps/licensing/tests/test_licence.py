import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Project
from apps.licensing import keys
from apps.licensing.models import Installation
from apps.licensing.service import get_status

TMP = Path(tempfile.mkdtemp())
PUBLIC = TMP / "public.txt"
PRIVATE = TMP / "private.pem"


def issue(install_id, days=365, users=25, modules="all", grace=15):
    out = StringIO()
    call_command("licence", "issue", "--private-key", str(PRIVATE), "--install", install_id,
                 "--licensee", "Selvam Builders", "--users", str(users), "--modules", modules, "--grace", str(grace),
                 "--expires", (timezone.localdate() + timedelta(days=days)).isoformat(), stdout=out)
    return out.getvalue().strip().splitlines()[-1]


@override_settings(LICENCE_PUBLIC_KEY_FILE=PUBLIC, LICENCE_TRIAL_DAYS=30, LICENCE_TRIAL_USERS=10)
class LicenceTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not PUBLIC.exists():
            with override_settings(LICENCE_PUBLIC_KEY_FILE=PUBLIC):
                call_command("licence", "keygen", "--private-key", str(PRIVATE), stdout=StringIO())

    def setUp(self):
        self.install = Installation.load()
        self.owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(self.owner)

    def activate(self, key):
        return self.client.post("/licence/", {"key": key})

    def test_keygen_refuses_to_overwrite(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("licence", "keygen", "--private-key", str(PRIVATE), stdout=StringIO())
        self.assertEqual(oct(PRIVATE.stat().st_mode)[-3:], "600")

    def test_new_install_is_on_trial(self):
        status = get_status()
        self.assertEqual(status.state, "trial")
        self.assertEqual(status.max_users, 10)
        self.assertContains(self.client.get("/"), "Trial version")

    def test_trial_over_makes_app_read_only(self):
        Installation.objects.update(installed_on=timezone.localdate() - timedelta(days=31))
        self.assertEqual(get_status().state, "expired")
        self.assertEqual(self.client.get("/projects/").status_code, 200)  # can still look
        resp = self.client.post("/projects/new/", {"name": "X", "code": "X", "status": "active",
                                                   "geofence_radius_m": 200, "contract_value": 0})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Project.objects.exists())
        # but the owner can still enter a key
        self.assertEqual(self.activate(issue(self.install.install_id)).status_code, 302)
        self.assertEqual(get_status().state, "valid")

    def test_valid_key_activates(self):
        resp = self.activate(issue(self.install.install_id))
        self.assertRedirects(resp, "/licence/")
        status = get_status()
        self.assertEqual(status.state, "valid")
        self.assertEqual(status.licence.licensee, "Selvam Builders")
        self.assertNotContains(self.client.get("/"), "Trial version")

    def test_key_for_another_installation_rejected(self):
        resp = self.activate(issue("DSQ-AAAA-BBBB-CCCC"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "was issued for installation DSQ-AAAA-BBBB-CCCC")
        self.assertEqual(Installation.load().licence_key, "")

    def test_tampered_key_rejected(self):
        key = issue(self.install.install_id, days=10)
        prefix, payload, sig = key.split(".")
        data = keys._b64d(payload).replace(b'"users":25', b'"users":99')
        forged = f"{prefix}.{keys._b64e(data)}.{sig}"
        resp = self.activate(forged)
        self.assertContains(resp, "not genuine")

    def test_key_with_line_breaks_accepted(self):
        key = issue(self.install.install_id)
        broken = "\n".join(key[i:i + 40] for i in range(0, len(key), 40))
        self.assertEqual(self.activate(broken).status_code, 302)

    def test_expiring_then_grace_then_read_only(self):
        self.activate(issue(self.install.install_id, days=10, grace=5))
        self.assertEqual(get_status().state, "expiring")
        self.assertContains(self.client.get("/"), "Please renew")

        self.activate(issue(self.install.install_id, days=-3, grace=5))
        self.assertEqual(get_status().state, "grace")
        self.assertEqual(self.client.post("/projects/new/", {}).status_code, 200)  # still works (form errors)

        self.activate(issue(self.install.install_id, days=-6, grace=5))
        self.assertEqual(get_status().state, "expired")
        self.assertEqual(self.client.post("/projects/new/", {}).status_code, 403)

    def test_turning_clock_back_does_not_help(self):
        self.activate(issue(self.install.install_id, days=10, grace=0))
        Installation.objects.update(last_seen_on=timezone.localdate() + timedelta(days=11))
        self.assertEqual(get_status().state, "expired")

    def test_unlicensed_module_is_switched_off(self):
        self.activate(issue(self.install.install_id, modules="attendance,payroll,progress,documents,billing"))
        self.assertEqual(self.client.get("/inventory/").status_code, 404)
        form = self.client.get("/settings/").context["form"]
        self.assertTrue(form.fields["module_inventory"].disabled)
        self.assertFalse(form.fields["module_progress"].disabled)

    def test_user_limit(self):
        self.activate(issue(self.install.install_id, users=2))
        data = {"username": "u2", "password": "Strong-pass-2026", "preferred_language": "en", "is_active": "on"}
        self.assertEqual(self.client.post("/accounts/users/new/", data).status_code, 302)
        resp = self.client.post("/accounts/users/new/", {**data, "username": "u3"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "allows 2 active users")
        # inactive users do not count
        self.assertEqual(self.client.post("/accounts/users/new/", {**{k: v for k, v in data.items() if k != "is_active"},
                                                                  "username": "u4"}).status_code, 302)

    def test_show_command(self):
        out = StringIO()
        call_command("licence", "show", issue(self.install.install_id), stdout=out)
        self.assertIn("Selvam Builders", out.getvalue())


@override_settings(LICENCE_PUBLIC_KEY_FILE=TMP / "missing.txt")
class UnconfiguredTests(TestCase):
    def test_no_public_key_means_no_limits(self):
        self.assertEqual(get_status().state, "unconfigured")
        owner = User.objects.create_superuser("owner", password="x")
        self.client.force_login(owner)
        self.assertContains(self.client.get("/licence/"), Installation.load().install_id)
