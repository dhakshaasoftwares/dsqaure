"""
Default configuration for a fresh client install. Every function is safe to
run again: it only adds what is missing and never overwrites edits.
"""

from decimal import Decimal

from django.contrib.auth.models import Group, Permission

from .models import CompanySettings, NumberSequence, Unit
from .permissions import MODULES_BY_KEY

ALL = ["view", "add", "change", "delete"]
VIEW = ["view"]

# role name -> {module key: actions or "extra"}
DEFAULT_ROLES = {
    "Admin": {key: ALL + ["extra"] for key in MODULES_BY_KEY},
    "Site Supervisor": {
        "projects": VIEW, "employees": VIEW, "attendance": ["view", "add", "change"],
        "masters": VIEW, "receipts": ["view", "add"], "stock": ["view", "add"],
        "progress": ["view", "add", "change"],
    },
    "Accountant": {
        "projects": VIEW, "employees": VIEW, "attendance": VIEW, "payroll": ALL, "advances": ALL,
        "payrules": VIEW, "masters": VIEW, "purchase": VIEW, "receipts": VIEW, "stock": VIEW,
        "quotations": VIEW, "agreements": VIEW,
    },
    "Storekeeper": {
        "projects": VIEW, "masters": ["view", "add", "change"], "purchase": ["view", "add", "change"],
        "receipts": ["view", "add"], "stock": ["view", "add"],
    },
    "Sales / Estimator": {
        "projects": ["view", "add", "change"], "quotations": ALL, "agreements": ALL, "progress": VIEW,
    },
    "Employee": {},
}

DEFAULT_UNITS = [
    ("Numbers", "Nos"), ("Bag", "Bag"), ("Kilogram", "Kg"), ("Tonne", "Ton"), ("Litre", "Ltr"),
    ("Metre", "m"), ("Square metre", "Sqm"), ("Cubic metre", "Cum"), ("Square feet", "Sqft"),
    ("Cubic feet", "Cft"), ("Running feet", "Rft"), ("Load", "Load"), ("Lump sum", "LS"),
]

DEFAULT_STAGES = [
    ("Site preparation & marking", 2), ("Excavation & foundation", 10), ("Plinth / basement", 6),
    ("Columns & beams", 10), ("Roof slab", 12), ("Brickwork / masonry", 12), ("Electrical conduits", 4),
    ("Plumbing & sanitary", 6), ("Plastering", 10), ("Flooring & tiling", 10), ("Doors & windows", 6),
    ("Painting", 8), ("Final finishing & handover", 4),
]

PAY_PRESETS = {
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

COUNTRY_PRESETS = {
    "india": {"currency_code": "INR", "currency_symbol": "₹", "number_grouping": "indian", "tax_label": "GST", "tax_code_label": "HSN/SAC",
              "timezone": "Asia/Kolkata", "financial_year_start_month": 4, "default_tax_rate": Decimal("18")},
    "none": {},
}

DEFAULT_AGREEMENT = """# CONSTRUCTION AGREEMENT

This agreement ({agreement_number}) is made on {agreement_date} between:

{company_name}, {company_address} (the "Contractor"), and

{client_name}, {client_address} (the "Owner").

## 1. Scope of work
The Contractor agrees to construct {project_name} at {site_address} as per the drawings, specifications and quotation agreed by both parties.

## 2. Contract value
The total contract value is {currency}{contract_value}, inclusive of the items listed in the agreed quotation. Additional work requested by the Owner will be charged separately after written approval.

## 3. Time for completion
Work will start on {start_date} and is expected to be completed by {completion_date}, subject to timely payments, availability of approvals and reasonable delays beyond the Contractor's control (weather, strikes, material shortages).

## 4. Payment schedule
{payment_schedule}

## 5. Materials and quality
All materials will be of the agreed brand and specification. The Owner may inspect the work at any reasonable time.

## 6. Changes and extra work
Any change to the approved drawings or specifications must be agreed in writing, along with its effect on cost and time.

## 7. Defects
The Contractor will rectify defects in workmanship reported within the defect liability period agreed by both parties.

## 8. Termination
Either party may terminate this agreement by written notice if the other party seriously breaches it and does not correct the breach within a reasonable time. Work completed up to that date will be paid for.

## 9. Disputes
Both parties will first try to settle any dispute by discussion. Unresolved disputes are subject to the courts having jurisdiction over the site.

Signed by both parties on the date written above."""


def ensure_roles():
    for role, modules in DEFAULT_ROLES.items():
        group, created = Group.objects.get_or_create(name=role)
        if not created:
            continue
        wanted = set()
        for key, actions in modules.items():
            module = MODULES_BY_KEY[key]
            for app, model in module["models"]:
                for action in actions:
                    if action != "extra":
                        wanted.add((app, f"{action}_{model}"))
            if "extra" in actions:
                for app, codename, _label in module.get("extra", []):
                    wanted.add((app, codename))
        perms = [p for p in Permission.objects.select_related("content_type")
                 .filter(codename__in=[c for _a, c in wanted])
                 if (p.content_type.app_label, p.codename) in wanted]
        group.permissions.set(perms)


def ensure_masters():
    NumberSequence.ensure_defaults()
    for name, symbol in DEFAULT_UNITS:
        if not Unit.objects.filter(symbol=symbol).exists() and not Unit.objects.filter(name=name).exists():
            Unit.objects.create(name=name, symbol=symbol)

    from apps.documents.models import DocumentTemplate
    from apps.progress.models import StageTemplate

    if not StageTemplate.objects.exists():
        for order, (name, weight) in enumerate(DEFAULT_STAGES, start=1):
            StageTemplate.objects.create(name=name, order=order, weight=weight)
    if not DocumentTemplate.objects.exists():
        DocumentTemplate.objects.create(name="Standard construction agreement", body=DEFAULT_AGREEMENT,
                                        is_default=True)


def apply_country_preset(preset):
    company = CompanySettings.load()
    for field, value in COUNTRY_PRESETS.get(preset, {}).items():
        setattr(company, field, value)
    company.save()

    from apps.payroll.models import PayComponent

    added = []
    for spec in PAY_PRESETS.get(preset, []):
        # Added switched off so nothing is deducted until the client reviews current rates.
        _obj, created = PayComponent.objects.get_or_create(code=spec["code"], defaults={**spec, "is_active": False})
        if created:
            added.append(spec["name"])
    return added


def ensure_defaults(preset=None):
    CompanySettings.load()
    ensure_roles()
    ensure_masters()
    return apply_country_preset(preset) if preset else []
