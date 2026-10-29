from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.forms import RoleForm
from apps.accounts.models import User
from apps.core.models import Project
from apps.employees.models import Employee
from apps.payroll.models import PayComponent, PayrollRun, SalaryAdvance


class RoleFormTests(TestCase):
    def test_grid_saves_permissions(self):
        form = RoleForm(data={"name": "Store", "perm_projects_view": "on", "perm_employees_view": "on", "perm_employees_add": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        group = form.save()
        codes = set(group.permissions.values_list("codename", flat=True))
        self.assertEqual(codes, {"view_project", "view_employee", "add_employee"})

    def test_grid_reflects_existing_permissions(self):
        form = RoleForm(data={"name": "R", "perm_employees_view": "on"})
        group = form.save() if form.is_valid() else None
        edit = RoleForm(instance=group)
        self.assertTrue(edit.fields["perm_employees_view"].initial)
        self.assertFalse(edit.fields["perm_employees_add"].initial)


class SmokeTests(TestCase):
    """Every screen renders for the owner, and a plain employee is kept out of admin screens."""

    @classmethod
    def setUpTestData(cls):
        call_command("setup_defaults", "--preset", "india", stdout=open("/dev/null", "w"))
        cls.owner = User.objects.create_superuser("owner", password="x")
        site = Project.objects.create(name="Site", code="S1")
        cls.emp = Employee.objects.create(code="E1", name="E1", default_project=site)
        cls.payroll_run = PayrollRun.objects.create(period_start="2026-10-01", period_end="2026-10-31")
        SalaryAdvance.objects.create(employee=cls.emp, date="2026-10-01", amount=100)
        cls.site = site

    def test_owner_pages(self):
        self.client.force_login(self.owner)
        urls = [
            reverse("core:dashboard"), reverse("core:menu"), reverse("core:project_list"),
            reverse("core:project_create"), reverse("core:project_update", args=[self.site.pk]),
            reverse("core:settings"), reverse("employees:list"), reverse("employees:create"),
            reverse("employees:detail", args=[self.emp.pk]), reverse("employees:update", args=[self.emp.pk]),
            reverse("attendance:mark"), reverse("attendance:register"), reverse("payroll:run_list"),
            reverse("payroll:run_create"), reverse("payroll:run_detail", args=[self.payroll_run.pk]),
            reverse("payroll:run_export", args=[self.payroll_run.pk]), reverse("payroll:advance_list"),
            reverse("payroll:advance_create"), reverse("payroll:component_list"),
            reverse("payroll:component_create"),
            reverse("payroll:component_update", args=[PayComponent.objects.first().pk]),
            reverse("accounts:user_list"), reverse("accounts:user_create"), reverse("accounts:role_list"),
            reverse("accounts:role_create"), reverse("accounts:role_update", args=[Group.objects.first().pk]),
            reverse("accounts:password_change"), reverse("payroll:my_payslips"),
            "/manifest.webmanifest", "/sw.js", "/offline/",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_login_page_and_redirect(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("employees:list")).status_code, 302)

    def test_employee_role_blocked_from_admin_screens(self):
        user = User.objects.create_user("emp", password="x")
        user.groups.add(Group.objects.get(name="Employee"))
        self.client.force_login(user)
        for url in [reverse("employees:list"), reverse("payroll:run_list"), reverse("accounts:user_list"),
                    reverse("core:settings")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_tamil_interface(self):
        self.owner.preferred_language = "ta"
        self.owner.save()
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("core:dashboard")), 'lang="ta"')
