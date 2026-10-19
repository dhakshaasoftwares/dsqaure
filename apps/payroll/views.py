import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.permissions import PermRequired

from .forms import PayComponentForm, PayrollRunForm, SalaryAdvanceForm
from .models import PayComponent, PayrollRun, Payslip, SalaryAdvance
from .services import finalize_run, generate_payslips


class RunList(PermRequired, ListView):
    permission_required = "payroll.view_payrollrun"
    model = PayrollRun
    template_name = "payroll/run_list.html"
    paginate_by = 30

    def get_queryset(self):
        return PayrollRun.objects.select_related("project").annotate(
            net=Sum("payslips__net_pay")).order_by("-period_end", "-pk")


class RunCreate(PermRequired, CreateView):
    permission_required = "payroll.add_payrollrun"
    model = PayrollRun
    form_class = PayrollRunForm
    template_name = "form.html"
    extra_context = {"title": gettext_lazy("New payroll"),
                     "intro": gettext_lazy("Pay is worked out from attendance in this period.")}

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        generate_payslips(self.object)
        return response

    def get_success_url(self):
        return reverse("payroll:run_detail", args=[self.object.pk])


@login_required
@permission_required("payroll.view_payrollrun", raise_exception=True)
def run_detail(request, pk):
    run = get_object_or_404(PayrollRun, pk=pk)
    slips = run.payslips.select_related("employee")
    totals = slips.aggregate(gross=Sum("gross_pay"), deductions=Sum("total_deductions"),
                             advances=Sum("advance_recovery"), net=Sum("net_pay"),
                             employer=Sum("employer_contributions"))
    return render(request, "payroll/run_detail.html", {"run": run, "slips": slips, "totals": totals})


@require_POST
@login_required
@permission_required("payroll.change_payrollrun", raise_exception=True)
def run_action(request, pk):
    run = get_object_or_404(PayrollRun, pk=pk)
    action = request.POST.get("action")
    if not run.is_draft:
        messages.error(request, _("This payroll is finalized and cannot be changed."))
    elif action == "recalculate":
        generate_payslips(run)
        messages.success(request, _("Payroll recalculated from latest attendance."))
    elif action == "finalize":
        finalize_run(run)
        messages.success(request, _("Payroll finalized. Advances have been updated."))
    elif action == "delete" and request.user.has_perm("payroll.delete_payrollrun"):
        run.delete()
        messages.success(request, _("Draft payroll deleted."))
        return redirect("payroll:run_list")
    return redirect("payroll:run_detail", pk=run.pk)


@login_required
def payslip_detail(request, pk):
    slip = get_object_or_404(Payslip.objects.select_related("employee", "run"), pk=pk)
    own = getattr(request.user, "employee", None) == slip.employee
    if not (own or request.user.has_perm("payroll.view_payslip")):
        return HttpResponse(status=403)
    return render(request, "payroll/payslip.html", {"slip": slip})


@login_required
def my_payslips(request):
    employee = getattr(request.user, "employee", None)
    slips = (Payslip.objects.filter(employee=employee, run__status=PayrollRun.Status.FINALIZED)
             .select_related("run") if employee else [])
    return render(request, "payroll/my_payslips.html", {"slips": slips})


@login_required
@permission_required("payroll.view_payrollrun", raise_exception=True)
def run_export(request, pk):
    """Spreadsheet of the run for bank upload or accountant."""
    run = get_object_or_404(PayrollRun, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="payroll_{run.period_start}_{run.period_end}.csv"'
    writer = csv.writer(response)
    writer.writerow(["Code", "Name", "Wage type", "Days worked", "Paid days", "OT hours", "Basic",
                     "Overtime", "Gross", "Deductions", "Advance recovery", "Net pay",
                     "Account name", "Account number", "Bank code", "UPI"])
    for s in run.payslips.select_related("employee"):
        e = s.employee
        writer.writerow([e.code, e.name, s.wage_type, s.days_worked, s.paid_days, s.overtime_hours,
                         s.basic_pay, s.overtime_pay, s.gross_pay, s.total_deductions,
                         s.advance_recovery, s.net_pay, e.bank_account_name, e.bank_account_number,
                         e.bank_ifsc, e.upi_id])
    return response


class AdvanceList(PermRequired, ListView):
    permission_required = "payroll.view_salaryadvance"
    model = SalaryAdvance
    template_name = "payroll/advance_list.html"
    paginate_by = 50

    def get_queryset(self):
        return SalaryAdvance.objects.select_related("employee").order_by("-date", "-pk")


class AdvanceCreate(PermRequired, CreateView):
    permission_required = "payroll.add_salaryadvance"
    model = SalaryAdvance
    form_class = SalaryAdvanceForm
    template_name = "form.html"
    success_url = reverse_lazy("payroll:advance_list")
    extra_context = {"title": gettext_lazy("Give salary advance")}

    def form_valid(self, form):
        form.instance.given_by = self.request.user
        return super().form_valid(form)


class ComponentList(PermRequired, ListView):
    permission_required = "payroll.view_paycomponent"
    model = PayComponent
    template_name = "payroll/component_list.html"


class ComponentCreate(PermRequired, CreateView):
    permission_required = "payroll.add_paycomponent"
    model = PayComponent
    form_class = PayComponentForm
    template_name = "form.html"
    success_url = reverse_lazy("payroll:component_list")
    extra_context = {"title": gettext_lazy("New pay rule")}


class ComponentUpdate(PermRequired, UpdateView):
    permission_required = "payroll.change_paycomponent"
    model = PayComponent
    form_class = PayComponentForm
    template_name = "form.html"
    success_url = reverse_lazy("payroll:component_list")
    extra_context = {"title": gettext_lazy("Edit pay rule")}
