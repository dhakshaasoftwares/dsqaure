"""
Permission catalogue used by the Roles screen.

Roles are Django groups. Each module lists the models whose standard
view/add/change/delete permissions the owner can tick for a role, plus any
special permissions (like approving purchase orders), so access is fully
configurable without code changes.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

ACTIONS = [
    ("view", _("View")),
    ("add", _("Add")),
    ("change", _("Edit")),
    ("delete", _("Delete")),
]

MODULES = [
    {"key": "projects", "label": _("Projects / sites"), "models": [("core", "project")]},
    {"key": "employees", "label": _("Employees"), "models": [("employees", "employee")]},
    {"key": "attendance", "label": _("Attendance (all staff)"), "models": [("attendance", "attendance")]},
    {"key": "payroll", "label": _("Payroll runs & payslips"),
     "models": [("payroll", "payrollrun"), ("payroll", "payslip")]},
    {"key": "advances", "label": _("Salary advances"), "models": [("payroll", "salaryadvance")]},
    {"key": "payrules", "label": _("Pay rules (allowances, PF, tax ...)"), "models": [("payroll", "paycomponent")]},
    {"key": "masters", "label": _("Materials, suppliers & stores"),
     "models": [("inventory", "material"), ("inventory", "supplier"), ("inventory", "location"),
                ("inventory", "materialcategory"), ("core", "unit")]},
    {"key": "purchase", "label": _("Purchase orders"), "models": [("inventory", "purchaseorder")],
     "extra": [("inventory", "approve_purchaseorder", _("Approve purchase orders"))]},
    {"key": "receipts", "label": _("Goods receipts"), "models": [("inventory", "goodsreceipt")]},
    {"key": "stock", "label": _("Stock transfers, issues & adjustments"),
     "models": [("inventory", "stocktransfer"), ("inventory", "materialissue"),
                ("inventory", "stockadjustment"), ("inventory", "stockmovement")]},
    {"key": "progress", "label": _("Building progress & site photos"),
     "models": [("progress", "projectstage"), ("progress", "progressupdate"), ("progress", "progressphoto")]},
    {"key": "quotations", "label": _("Clients & quotations"),
     "models": [("documents", "client"), ("documents", "quotation"), ("documents", "workitem")]},
    {"key": "agreements", "label": _("Agreements"),
     "models": [("documents", "agreement"), ("documents", "documenttemplate")]},
    {"key": "billing", "label": _("Client invoices & payments received"),
     "models": [("billing", "invoice"), ("billing", "clientpayment")]},
    {"key": "sharing", "label": _("Send documents by email / WhatsApp"),
     "models": [("sharing", "sentmessage"), ("sharing", "sharelink")]},
    {"key": "settings", "label": _("Company settings & numbering"),
     "models": [("core", "companysettings"), ("core", "numbersequence"), ("progress", "stagetemplate")]},
    {"key": "users", "label": _("Users & roles"), "models": [("accounts", "user"), ("auth", "group")]},
    {"key": "audit", "label": _("Audit log"), "models": [("core", "auditlog")]},
]

MODULES_BY_KEY = {m["key"]: m for m in MODULES}


class PermRequired(LoginRequiredMixin, PermissionRequiredMixin):
    """Login + permission check; logged-in users without access get a 403 page."""

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied
        return super().handle_no_permission()
