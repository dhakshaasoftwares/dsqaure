"""
First-run setup: company settings row, default roles and (optionally) a
country preset of pay rules. Safe to run again – it never overwrites edits.

    python manage.py setup_defaults                 # roles only, no statutory rules
    python manage.py setup_defaults --preset india  # + PF / ESI / Professional tax samples
"""

from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from apps.core.models import CompanySettings
from apps.core.permissions import MODULES
from apps.payroll.models import PayComponent

ALL = ["view", "add", "change", "delete"]

# role name -> {module index in MODULES: allowed actions}
DEFAULT_ROLES = {
    "Admin": {i: ALL for i in range(len(MODULES))},
    "Site Supervisor": {0: ["view"], 1: ["view"], 2: ["view", "add", "change"]},
    "Accountant": {1: ["view"], 2: ["view"], 3: ALL, 4: ALL, 5: ["view"]},
    "Storekeeper": {0: ["view"]},
    "Employee": {},
}

PRESETS = {
    "india": [
        dict(name="Provident Fund (PF) – employee", code="pf-employee", kind="deduction", method="pct_basic",
             value=Decimal("12"), base_ceiling=Decimal("15000"), applies_to="monthly"),
        dict(name="Provident Fund (PF) – employer", code="pf-employer", kind="employer", method="pct_basic",
             value=Decimal("12"), base_ceiling=Decimal("15000"), applies_to="monthly"),
        dict(name="ESI – employee", code="esi-employee", kind="deduction", method="pct_gross",
             value=Decimal("0.75"), eligible_max_gross=Decimal("21000"), round_to_whole=False),
        dict(name="ESI – employer", code="esi-employer", kind="employer", method="pct_gross",
             value=Decimal("3.25"), eligible_max_gross=Decimal("21000"), round_to_whole=False),
        dict(name="Professional tax", code="professional-tax", kind="deduction", method="fixed",
             value=Decimal("200"), applies_to="monthly"),
        dict(name="Food allowance", code="food-allowance", kind="earning", method="per_day",
             value=Decimal("50")),
    ],
    "none": [],
}


class Command(BaseCommand):
    help = "Create company settings, default roles and optional pay-rule preset"

    def add_arguments(self, parser):
        parser.add_argument("--preset", choices=sorted(PRESETS), default="none")

    def handle(self, *args, preset, **options):
        company = CompanySettings.load()
        if preset == "india":
            company.currency_code, company.currency_symbol, company.tax_label = "INR", "₹", "GST"
            company.save()

        for role, modules in DEFAULT_ROLES.items():
            group, created = Group.objects.get_or_create(name=role)
            if not created:
                continue
            perms = []
            for index, actions in modules.items():
                for app, model in MODULES[index][1]:
                    for action in actions:
                        perms += list(Permission.objects.filter(
                            content_type__app_label=app, codename=f"{action}_{model}"))
            group.permissions.set(perms)
            self.stdout.write(f"Created role: {role}")

        for spec in PRESETS[preset]:
            # Created inactive and opt-in so nothing is deducted until reviewed.
            _obj, created = PayComponent.objects.get_or_create(
                code=spec["code"], defaults={**spec, "is_active": False})
            if created:
                self.stdout.write(f"Added pay rule (inactive – review and switch on): {spec['name']}")

        self.stdout.write(self.style.SUCCESS("Setup complete."))
