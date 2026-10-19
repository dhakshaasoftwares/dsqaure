from django.db.models import Q
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.permissions import PermRequired

from .forms import EmployeeForm
from .models import Employee


class EmployeeList(PermRequired, ListView):
    permission_required = "employees.view_employee"
    model = Employee
    template_name = "employees/employee_list.html"
    paginate_by = 50

    def get_queryset(self):
        qs = Employee.objects.select_related("default_project")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(phone__icontains=q)
                           | Q(designation__icontains=q))
        if self.request.GET.get("show") != "all":
            qs = qs.filter(is_active=True)
        return qs


class EmployeeDetail(PermRequired, DetailView):
    permission_required = "employees.view_employee"
    model = Employee
    template_name = "employees/employee_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recent_attendance"] = self.object.attendance.select_related("project")[:14]
        ctx["advances"] = self.object.advances.all()[:10]
        return ctx


class EmployeeCreate(PermRequired, CreateView):
    permission_required = "employees.add_employee"
    model = Employee
    form_class = EmployeeForm
    template_name = "form.html"
    extra_context = {"title": _("New employee")}

    def get_success_url(self):
        return reverse_lazy("employees:detail", args=[self.object.pk])


class EmployeeUpdate(PermRequired, UpdateView):
    permission_required = "employees.change_employee"
    model = Employee
    form_class = EmployeeForm
    template_name = "form.html"
    extra_context = {"title": _("Edit employee")}

    def get_success_url(self):
        return reverse_lazy("employees:detail", args=[self.object.pk])
