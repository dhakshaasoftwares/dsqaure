from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, ListView, UpdateView
from django.views.static import serve
from django.conf import settings

from apps.accounts.models import User
from apps.attendance.models import Attendance
from apps.employees.models import Employee

from .forms import CompanySettingsForm, NumberSequenceForm, ProjectForm, SetupForm
from .models import AuditLog, CompanySettings, NumberSequence, Project
from .permissions import PermRequired
from .setup import ensure_defaults


@login_required
def dashboard(request):
    today = timezone.localdate()
    company = request.company
    context = {"today": today}
    user = request.user
    employee = getattr(user, "employee", None)
    if employee and company.module_attendance:
        context["my_attendance"] = Attendance.objects.filter(employee=employee, date=today).first()
    if company.module_attendance and user.has_perm("attendance.view_attendance"):
        counts = Attendance.objects.filter(date=today).values("status").annotate(n=Count("id"))
        by_status = {row["status"]: row["n"] for row in counts}
        context["today_counts"] = {
            "present": by_status.get("present", 0) + by_status.get("half_day", 0),
            "absent": by_status.get("absent", 0),
            "leave": by_status.get("leave", 0),
        }
        context["active_employees"] = Employee.objects.filter(is_active=True).count()
    if user.has_perm("core.view_project"):
        sites = Project.objects.filter(status=Project.Status.ACTIVE).annotate(on_site=Count(
            "attendance", filter=Q(attendance__date=today, attendance__status__in=["present", "half_day"])))
        if company.module_progress:
            from apps.progress.services import overall_percent_map

            pct = overall_percent_map(sites)
            for site in sites:
                site.progress = pct.get(site.pk)
        context["sites"] = sites
    if company.module_inventory and user.has_perm("inventory.view_stockmovement"):
        from apps.inventory.services import low_stock

        context["low_stock"] = low_stock()[:8]
    if company.module_billing and user.has_perm("billing.view_invoice"):
        from apps.billing.services import receivables

        due = receivables(company)
        context["receivable_total"] = sum((r["balance"] for r in due), 0)
        context["overdue"] = [r for r in due if r["overdue"]][:8]
    if company.module_inventory and user.has_perm("inventory.approve_purchaseorder"):
        from apps.inventory.models import PurchaseOrder

        context["pos_to_approve"] = PurchaseOrder.objects.filter(status=PurchaseOrder.Status.DRAFT).count()
    return render(request, "core/dashboard.html", context)


@login_required
def menu(request):
    return render(request, "core/menu.html")


def setup(request):
    """First-run wizard for a brand-new client install. Disabled once any user exists."""
    if User.objects.exists():
        return redirect("accounts:login")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        with transaction.atomic():
            ensure_defaults(data["preset"])
            company = CompanySettings.load()
            company.name = data["company_name"]
            company.phone = data["phone"]
            company.address = data["address"]
            company.signatory_name = data["owner_name"]
            company.save()
            first, _sep, last = data["owner_name"].partition(" ")
            owner = User.objects.create_superuser(
                data["username"], password=data["password1"], first_name=first, last_name=last,
                preferred_language=data["language"])
        login(request, owner)
        messages.success(request, _("Welcome! Check the company settings and switch on the modules you need."))
        return redirect("core:settings")
    return render(request, "core/setup.html", {"form": form})


# Uploaded file → permission needed to see it. Owners always can.
MEDIA_RULES = [
    ("company/", None),
    ("employees/photos/", "employees.view_employee"),
    ("employees/id/", "employees.view_employee"),
    ("attendance/", "attendance.view_attendance"),
    ("progress/", "progress.view_progressphoto"),
]


@login_required
def protected_media(request, path):
    user = request.user
    allowed = user.is_superuser
    if not allowed:
        for prefix, perm in MEDIA_RULES:
            if path.startswith(prefix):
                allowed = perm is None or user.has_perm(perm)
                break
    if not allowed:
        employee = getattr(user, "employee", None)
        if employee and (employee.photo.name == path
                         or employee.attendance.filter(check_in_photo=path).exists()):
            allowed = True
    if not allowed:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)


class ProjectList(PermRequired, ListView):
    permission_required = "core.view_project"
    model = Project
    template_name = "core/project_list.html"

    def get_queryset(self):
        qs = Project.objects.select_related("client")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuses"] = Project.Status.choices
        if self.request.company.module_progress:
            from apps.progress.services import overall_percent_map

            pct = overall_percent_map(ctx["object_list"])
            for p in ctx["object_list"]:
                p.progress = pct.get(p.pk)
        return ctx


@login_required
@permission_required("core.view_project", raise_exception=True)
def project_detail(request, pk):
    """One page with everything about a site: progress, photos, material, labour, documents."""
    project = get_object_or_404(Project.objects.select_related("client"), pk=pk)
    company = request.company
    user = request.user
    ctx = {"project": project}
    today = timezone.localdate()
    month_start = today.replace(day=1)

    if company.module_progress and user.has_perm("progress.view_projectstage"):
        from apps.progress.services import overall_percent

        ctx["stages"] = project.stages.all()
        ctx["overall"] = overall_percent(project)
        ctx["photos"] = project.photos.all()[:8]

    if company.module_attendance and user.has_perm("attendance.view_attendance"):
        att = Attendance.objects.filter(project=project)
        ctx["mandays_month"] = sum(a.day_value for a in att.filter(date__gte=month_start))
        ctx["mandays_total"] = sum(a.day_value for a in att)
        ctx["on_site_today"] = att.filter(date=today, status__in=["present", "half_day"]).count()

    if company.module_inventory and user.has_perm("inventory.view_stockmovement"):
        from apps.inventory.models import StockMovement
        from apps.inventory.services import balances

        location = getattr(project, "stock_location", None)
        if location:
            ctx["site_stock"] = [b for b in balances(location=location) if b["qty"]][:15]
            value = ExpressionWrapper(-F("quantity") * F("rate"), output_field=DecimalField(max_digits=16, decimal_places=2))
            consumed = (StockMovement.objects.filter(location=location, kind=StockMovement.Kind.ISSUE)
                        .values("material__name", "material__unit__symbol")
                        .annotate(qty=Sum("quantity"), value=Sum(value)).order_by("material__name"))
            ctx["consumed"] = [dict(c, qty=-c["qty"]) for c in consumed]
            ctx["material_cost"] = sum((c["value"] or 0) for c in consumed)

    if company.module_billing and user.has_perm("billing.view_invoice"):
        from apps.billing.models import Invoice

        invoices = list(project.invoices.exclude(status=Invoice.Status.CANCELLED)
                        .prefetch_related("lines", "payments"))
        amounts = [inv.amounts(company) for inv in invoices if inv.status == Invoice.Status.ISSUED]
        ctx["billing"] = {
            "billed": sum((a["subtotal"] for a in amounts), 0),
            "received": sum((a["paid"] for a in amounts), 0),
            "outstanding": sum((a["balance"] for a in amounts), 0),
            "agreements": project.agreements.exclude(status="cancelled"),
        }

    if company.module_documents and user.has_perm("documents.view_quotation"):
        ctx["quotations"] = project.quotations.select_related("client")[:10]
        ctx["agreements"] = project.agreements.all()[:10]
    return render(request, "core/project_detail.html", ctx)


class ProjectCreate(PermRequired, CreateView):
    permission_required = "core.add_project"
    model = Project
    form_class = ProjectForm
    template_name = "core/project_form.html"
    extra_context = {"title": _("New project / site")}

    def get_success_url(self):
        return reverse_lazy("core:project_detail", args=[self.object.pk])


class ProjectUpdate(PermRequired, UpdateView):
    permission_required = "core.change_project"
    model = Project
    form_class = ProjectForm
    template_name = "core/project_form.html"
    extra_context = {"title": _("Edit project / site")}

    def get_success_url(self):
        return reverse_lazy("core:project_detail", args=[self.object.pk])


class SettingsUpdate(PermRequired, UpdateView):
    permission_required = "core.change_companysettings"
    form_class = CompanySettingsForm
    template_name = "core/settings.html"
    success_url = reverse_lazy("core:settings")
    extra_context = {"title": _("Company settings")}

    def get_object(self, queryset=None):
        return CompanySettings.load()

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        licence = getattr(self.request, "licence", None)
        if licence is not None:
            for name, field in form.fields.items():
                if name.startswith("module_") and not licence.module_allowed(name[len("module_"):]):
                    field.disabled = True
                    field.help_text = _("Not included in your licence")
        return form

    def form_valid(self, form):
        messages.success(self.request, _("Settings saved"))
        return super().form_valid(form)


@login_required
@permission_required("core.view_companysettings", raise_exception=True)
def configuration(request):
    """Index of every configurable list, so a new client can be set up from one place."""
    return render(request, "core/configuration.html")


class NumberSequenceList(PermRequired, ListView):
    permission_required = "core.view_numbersequence"
    model = NumberSequence
    template_name = "core/number_series.html"

    def get_queryset(self):
        NumberSequence.ensure_defaults()
        today = timezone.localdate()
        start = self.request.company.financial_year_start_month
        items = list(NumberSequence.objects.all())
        for seq in items:
            value = 1 if seq.period_for(today, start) != seq.period else seq.next_value
            seq.preview = seq.render(value, today, start)
        return items


class NumberSequenceUpdate(PermRequired, UpdateView):
    permission_required = "core.change_numbersequence"
    model = NumberSequence
    form_class = NumberSequenceForm
    template_name = "form.html"
    success_url = reverse_lazy("core:number_series")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = _("Number format: %(doc)s") % {"doc": self.object.label}
        ctx["intro"] = _("Example: PO/{FY}/{SEQ} gives PO/2026-27/0001. The running number restarts "
                         "every financial year when {FY} is used.")
        return ctx


class AuditLogList(PermRequired, ListView):
    permission_required = "core.view_auditlog"
    model = AuditLog
    template_name = "core/audit_log.html"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(object_repr__icontains=q) | Q(model__icontains=q) | Q(user__username__icontains=q))
        if self.request.GET.get("action"):
            qs = qs.filter(action=self.request.GET["action"])
        return qs
