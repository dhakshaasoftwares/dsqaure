"""
Permission catalogue used by the Roles screen.

Roles are Django groups. Each module below lists the models whose standard
view/add/change/delete permissions the owner can tick for a role, so access is
fully configurable without code changes.
"""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.utils.translation import gettext_lazy as _

ACTIONS = [
    ("view", _("View")),
    ("add", _("Add")),
    ("change", _("Edit")),
    ("delete", _("Delete")),
]

# (module label, [(app_label, model_name), ...])
MODULES = [
    (_("Projects / sites"), [("core", "project")]),
    (_("Employees"), [("employees", "employee")]),
    (_("Attendance (all staff)"), [("attendance", "attendance")]),
    (_("Payroll runs & payslips"), [("payroll", "payrollrun"), ("payroll", "payslip")]),
    (_("Salary advances"), [("payroll", "salaryadvance")]),
    (_("Pay rules (allowances, PF, tax ...)"), [("payroll", "paycomponent")]),
    (_("Company settings"), [("core", "companysettings")]),
    (_("Users & roles"), [("accounts", "user"), ("auth", "group")]),
]


def codenames_for(models, action):
    return [f"{app}.{action}_{model}" for app, model in models]


class PermRequired(LoginRequiredMixin, PermissionRequiredMixin):
    """Login + permission check; logged-in users without access get a 403 page."""

    raise_exception = False

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return super().handle_no_permission()
