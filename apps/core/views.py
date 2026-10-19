from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView
from django.shortcuts import render

from apps.attendance.models import Attendance
from apps.employees.models import Employee

from .forms import CompanySettingsForm, ProjectForm
from .models import CompanySettings, Project
from .permissions import PermRequired


@login_required
def dashboard(request):
    today = timezone.localdate()
    context = {"today": today}
    user = request.user
    employee = getattr(user, "employee", None)
    if employee:
        context["my_attendance"] = Attendance.objects.filter(employee=employee, date=today).first()
    if user.has_perm("attendance.view_attendance"):
        counts = Attendance.objects.filter(date=today).values("status").annotate(n=Count("id"))
        by_status = {row["status"]: row["n"] for row in counts}
        context["today_counts"] = {
            "present": by_status.get("present", 0) + by_status.get("half_day", 0),
            "absent": by_status.get("absent", 0),
            "leave": by_status.get("leave", 0),
        }
        context["active_employees"] = Employee.objects.filter(is_active=True).count()
        context["sites"] = (
            Project.objects.filter(status=Project.Status.ACTIVE)
            .annotate(on_site=Count("attendance", filter=Q(
                attendance__date=today, attendance__status__in=["present", "half_day"])))
        )
    return render(request, "core/dashboard.html", context)


@login_required
def menu(request):
    return render(request, "core/menu.html")


class ProjectList(PermRequired, ListView):
    permission_required = "core.view_project"
    model = Project
    template_name = "core/project_list.html"


class ProjectCreate(PermRequired, CreateView):
    permission_required = "core.add_project"
    model = Project
    form_class = ProjectForm
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:project_list")
    extra_context = {"title": _("New project / site")}


class ProjectUpdate(PermRequired, UpdateView):
    permission_required = "core.change_project"
    model = Project
    form_class = ProjectForm
    template_name = "core/project_form.html"
    success_url = reverse_lazy("core:project_list")
    extra_context = {"title": _("Edit project / site")}


class SettingsUpdate(PermRequired, UpdateView):
    permission_required = "core.change_companysettings"
    form_class = CompanySettingsForm
    template_name = "form.html"
    success_url = reverse_lazy("core:settings")
    extra_context = {"title": _("Company settings")}

    def get_object(self, queryset=None):
        return CompanySettings.load()

    def form_valid(self, form):
        messages.success(self.request, _("Settings saved"))
        return super().form_valid(form)
