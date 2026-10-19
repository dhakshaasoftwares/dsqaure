"""
Salary calculation.

The calculation is a pure function of: employee wage settings, attendance in
the period, company settings, configured pay components and open advances.
It never writes to the database; PayrollRun generation stores the result.
"""

import calendar
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.attendance.models import Attendance
from apps.core.models import CompanySettings
from apps.employees.models import Employee

from .models import PayComponent, Payslip, PayrollRun, SalaryAdvance

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class SalaryResult:
    days_worked: Decimal = ZERO
    paid_days: Decimal = ZERO
    overtime_hours: Decimal = ZERO
    basic_pay: Decimal = ZERO
    overtime_pay: Decimal = ZERO
    gross_pay: Decimal = ZERO
    total_deductions: Decimal = ZERO
    advance_recovery: Decimal = ZERO
    net_pay: Decimal = ZERO
    employer_contributions: Decimal = ZERO
    lines: list = field(default_factory=list)
    advance_allocations: list = field(default_factory=list)


def daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def monthly_per_day_rate(employee, period_start, company):
    days_in_month = calendar.monthrange(period_start.year, period_start.month)[1]
    if company.monthly_salary_basis == "fixed30":
        basis = 30
    elif company.monthly_salary_basis == "working":
        month_start = period_start.replace(day=1)
        month_end = period_start.replace(day=days_in_month)
        basis = sum(1 for d in daterange(month_start, month_end) if d.weekday() != company.weekly_off_day)
    else:
        basis = days_in_month
    return Decimal(employee.wage_rate) / Decimal(basis)


def components_for(employee):
    wage_scopes = [PayComponent.AppliesTo.ALL, employee.wage_type]
    everyone = PayComponent.objects.filter(is_active=True, apply_to_everyone=True, applies_to__in=wage_scopes)
    chosen = employee.pay_components.filter(is_active=True, applies_to__in=wage_scopes) if employee.pk else []
    seen, result = set(), []
    for comp in list(everyone) + list(chosen):
        if comp.pk not in seen:
            seen.add(comp.pk)
            result.append(comp)
    return sorted(result, key=lambda c: (c.sort_order, c.name))


def component_amount(comp, basic, gross, days_worked):
    if comp.eligible_max_gross is not None and gross > comp.eligible_max_gross:
        return ZERO
    if comp.method == PayComponent.Method.FIXED:
        amount = comp.value
    elif comp.method == PayComponent.Method.PER_DAY:
        amount = comp.value * days_worked
    else:
        base = basic if comp.method == PayComponent.Method.PERCENT_BASIC else gross
        if comp.base_ceiling is not None:
            base = min(base, comp.base_ceiling)
        amount = base * comp.value / Decimal("100")
    if comp.max_amount is not None:
        amount = min(amount, comp.max_amount)
    if comp.round_to_whole:
        amount = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return money(amount)


def calculate_salary(employee, period_start, period_end, company=None, attendance=None, advances=None):
    company = company or CompanySettings.load()
    if attendance is None:
        attendance = Attendance.objects.filter(employee=employee, date__range=(period_start, period_end))
    if advances is None:
        advances = SalaryAdvance.objects.filter(employee=employee, date__lte=period_end)

    result = SalaryResult()
    by_date = {a.date: a for a in attendance}

    days_worked = sum((a.day_value for a in by_date.values()), ZERO)
    overtime_hours = sum((Decimal(a.overtime_hours) for a in by_date.values()), ZERO)

    if employee.wage_type == Employee.WageType.MONTHLY:
        per_day = monthly_per_day_rate(employee, period_start, company)
        paid_days = days_worked
        for a in by_date.values():
            if a.status == Attendance.Status.HOLIDAY:
                paid_days += 1
            elif a.status == Attendance.Status.LEAVE and company.paid_leave_for_monthly:
                paid_days += 1
        if company.paid_weekly_off_for_monthly and company.monthly_salary_basis != "working":
            # A weekly-off day is paid unless the day was explicitly marked
            # otherwise (worked days are already counted above).
            for day in daterange(period_start, period_end):
                if day.weekday() == company.weekly_off_day:
                    record = by_date.get(day)
                    if record is None or record.status == Attendance.Status.WEEK_OFF:
                        paid_days += 1
    else:
        per_day = Decimal(employee.wage_rate)
        paid_days = days_worked

    hourly = employee.overtime_hourly_rate
    if hourly is None:
        hours = company.working_hours_per_day or Decimal("8")
        hourly = per_day / hours * company.overtime_multiplier

    result.days_worked = days_worked
    result.paid_days = paid_days
    result.overtime_hours = overtime_hours
    result.basic_pay = money(per_day * paid_days)
    result.overtime_pay = money(Decimal(hourly) * overtime_hours)

    comps = components_for(employee)
    gross = result.basic_pay + result.overtime_pay
    for comp in comps:
        if comp.kind == PayComponent.Kind.EARNING:
            amount = component_amount(comp, result.basic_pay, gross, days_worked)
            if amount:
                result.lines.append({"name": comp.name, "kind": "earning", "amount": str(amount)})
                gross += amount
    result.gross_pay = money(gross)

    deductions = ZERO
    for comp in comps:
        if comp.kind == PayComponent.Kind.EARNING:
            continue
        amount = component_amount(comp, result.basic_pay, result.gross_pay, days_worked)
        if not amount:
            continue
        result.lines.append({"name": comp.name, "kind": comp.kind, "amount": str(amount)})
        if comp.kind == PayComponent.Kind.DEDUCTION:
            deductions += amount
        else:
            result.employer_contributions += amount

    # Recover advances oldest first without taking pay below zero.
    available = max(result.gross_pay - deductions, ZERO)
    for adv in advances:
        balance = adv.amount - adv.recovered_amount
        if balance <= 0 or available <= 0:
            continue
        take = min(balance, adv.installment or balance, available)
        result.advance_allocations.append({"advance_id": adv.pk, "amount": str(money(take))})
        result.advance_recovery += take
        available -= take

    result.advance_recovery = money(result.advance_recovery)
    result.total_deductions = money(deductions)
    result.employer_contributions = money(result.employer_contributions)
    result.net_pay = money(result.gross_pay - result.total_deductions - result.advance_recovery)
    return result


def employees_for_run(run):
    qs = Employee.objects.filter(is_active=True)
    if run.wage_type:
        qs = qs.filter(wage_type=run.wage_type)
    if run.project_id:
        qs = qs.filter(attendance__project=run.project,
                       attendance__date__range=(run.period_start, run.period_end)).distinct()
    return qs


@transaction.atomic
def generate_payslips(run):
    if not run.is_draft:
        raise ValueError("Finalized payroll cannot be regenerated")
    company = CompanySettings.load()
    run.payslips.all().delete()
    for employee in employees_for_run(run):
        r = calculate_salary(employee, run.period_start, run.period_end, company=company)
        Payslip.objects.create(
            run=run,
            employee=employee,
            wage_type=employee.wage_type,
            wage_rate=employee.wage_rate,
            days_worked=r.days_worked,
            paid_days=r.paid_days,
            overtime_hours=r.overtime_hours,
            basic_pay=r.basic_pay,
            overtime_pay=r.overtime_pay,
            gross_pay=r.gross_pay,
            total_deductions=r.total_deductions,
            advance_recovery=r.advance_recovery,
            net_pay=r.net_pay,
            employer_contributions=r.employer_contributions,
            lines=r.lines,
            advance_allocations=r.advance_allocations,
        )


@transaction.atomic
def finalize_run(run):
    if not run.is_draft:
        return
    for slip in run.payslips.all():
        for alloc in slip.advance_allocations:
            adv = SalaryAdvance.objects.select_for_update().get(pk=alloc["advance_id"])
            adv.recovered_amount = min(adv.amount, adv.recovered_amount + Decimal(alloc["amount"]))
            adv.save(update_fields=["recovered_amount"])
    run.status = PayrollRun.Status.FINALIZED
    run.finalized_at = timezone.now()
    run.save(update_fields=["status", "finalized_at"])
