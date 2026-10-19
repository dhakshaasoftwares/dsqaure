from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.attendance.models import Attendance
from apps.core.models import CompanySettings
from apps.employees.models import Employee
from apps.payroll.models import PayComponent, PayrollRun, SalaryAdvance
from apps.payroll.services import calculate_salary, finalize_run, generate_payslips

D = Decimal


def mark(employee, day, status="present", ot=0):
    return Attendance.objects.create(employee=employee, date=day, status=status, overtime_hours=D(ot))


class DailyWageTests(TestCase):
    def setUp(self):
        self.company = CompanySettings.load()
        self.emp = Employee.objects.create(code="E1", name="Murugan", wage_type="daily", wage_rate=D("800"))
        self.start, self.end = date(2026, 10, 5), date(2026, 10, 11)

    def test_days_half_days_and_absence(self):
        mark(self.emp, date(2026, 10, 5))
        mark(self.emp, date(2026, 10, 6))
        mark(self.emp, date(2026, 10, 7), "half_day")
        mark(self.emp, date(2026, 10, 8), "absent")
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.days_worked, D("2.5"))
        self.assertEqual(r.basic_pay, D("2000.00"))
        self.assertEqual(r.net_pay, D("2000.00"))

    def test_overtime_uses_hours_and_multiplier(self):
        self.company.working_hours_per_day = D("8")
        self.company.overtime_multiplier = D("1.5")
        self.company.save()
        mark(self.emp, date(2026, 10, 5), ot=2)
        r = calculate_salary(self.emp, self.start, self.end)
        # 800 / 8 * 1.5 = 150 per hour
        self.assertEqual(r.overtime_pay, D("300.00"))
        self.assertEqual(r.gross_pay, D("1100.00"))

    def test_explicit_overtime_rate_wins(self):
        self.emp.overtime_hourly_rate = D("120")
        self.emp.save()
        mark(self.emp, date(2026, 10, 5), ot=1)
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).overtime_pay, D("120.00"))

    def test_no_statutory_rules_means_no_deductions(self):
        for d in range(5):
            mark(self.emp, self.start + timedelta(days=d))
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.total_deductions, D("0"))
        self.assertEqual(r.lines, [])


class MonthlySalaryTests(TestCase):
    def setUp(self):
        self.company = CompanySettings.load()
        self.company.weekly_off_day = 6  # Sunday
        self.company.save()
        self.emp = Employee.objects.create(code="M1", name="Priya", wage_type="monthly", wage_rate=D("31000"))
        # October 2026: 31 days, Sundays on 4, 11, 18, 25 → 27 working days
        self.start, self.end = date(2026, 10, 1), date(2026, 10, 31)

    def mark_all_working_days(self):
        day = self.start
        while day <= self.end:
            if day.weekday() != 6:
                mark(self.emp, day)
            day += timedelta(days=1)

    def test_full_month_calendar_basis_pays_full_salary(self):
        self.mark_all_working_days()
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.paid_days, D("31"))
        self.assertEqual(r.basic_pay, D("31000.00"))

    def test_full_month_working_basis_pays_full_salary(self):
        self.company.monthly_salary_basis = "working"
        self.company.save()
        self.mark_all_working_days()
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.paid_days, D("27"))
        self.assertEqual(r.basic_pay, D("31000.00"))

    def test_absence_reduces_pay_and_paid_leave_does_not(self):
        self.mark_all_working_days()
        Attendance.objects.filter(employee=self.emp, date=date(2026, 10, 5)).update(status="absent")
        Attendance.objects.filter(employee=self.emp, date=date(2026, 10, 6)).update(status="leave")
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.paid_days, D("30"))
        self.assertEqual(r.basic_pay, D("30000.00"))

    def test_unpaid_leave_setting(self):
        self.company.paid_leave_for_monthly = False
        self.company.save()
        self.mark_all_working_days()
        Attendance.objects.filter(employee=self.emp, date=date(2026, 10, 6)).update(status="leave")
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).paid_days, D("30"))


class PayComponentTests(TestCase):
    def setUp(self):
        self.emp = Employee.objects.create(code="M2", name="Kumar", wage_type="monthly", wage_rate=D("30000"))
        self.start, self.end = date(2026, 10, 1), date(2026, 10, 31)
        day = self.start
        while day <= self.end:
            mark(self.emp, day, "present" if day.weekday() != 6 else "week_off")
            day += timedelta(days=1)

    def test_percentage_with_ceiling_like_pf(self):
        PayComponent.objects.create(name="PF", code="pf", kind="deduction", method="pct_basic",
                                    value=D("12"), base_ceiling=D("15000"), apply_to_everyone=True)
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.total_deductions, D("1800.00"))
        self.assertEqual(r.net_pay, D("28200.00"))

    def test_eligibility_limit_like_esi(self):
        PayComponent.objects.create(name="ESI", code="esi", kind="deduction", method="pct_gross",
                                    value=D("0.75"), eligible_max_gross=D("21000"), apply_to_everyone=True)
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).total_deductions, D("0"))

    def test_employer_contribution_not_deducted(self):
        PayComponent.objects.create(name="PF employer", code="pfe", kind="employer", method="pct_basic",
                                    value=D("12"), apply_to_everyone=True)
        r = calculate_salary(self.emp, self.start, self.end)
        self.assertEqual(r.employer_contributions, D("3600.00"))
        self.assertEqual(r.net_pay, D("30000.00"))

    def test_component_only_for_selected_employee(self):
        bonus = PayComponent.objects.create(name="Bonus", code="bonus", kind="earning", method="fixed",
                                            value=D("1000"))
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).gross_pay, D("30000.00"))
        self.emp.pay_components.add(bonus)
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).gross_pay, D("31000.00"))

    def test_wage_type_scope(self):
        PayComponent.objects.create(name="Daily food", code="food", kind="earning", method="per_day",
                                    value=D("50"), applies_to="daily", apply_to_everyone=True)
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).gross_pay, D("30000.00"))

    def test_inactive_component_ignored(self):
        PayComponent.objects.create(name="PT", code="pt", kind="deduction", method="fixed",
                                    value=D("200"), apply_to_everyone=True, is_active=False)
        self.assertEqual(calculate_salary(self.emp, self.start, self.end).total_deductions, D("0"))


class AdvanceAndRunTests(TestCase):
    def setUp(self):
        self.emp = Employee.objects.create(code="E9", name="Ravi", wage_type="daily", wage_rate=D("1000"))
        for d in range(5):
            mark(self.emp, date(2026, 10, 5) + timedelta(days=d))

    def test_installment_recovered_and_applied_on_finalize(self):
        adv = SalaryAdvance.objects.create(employee=self.emp, date=date(2026, 10, 1),
                                           amount=D("3000"), installment=D("1000"))
        run = PayrollRun.objects.create(period_start=date(2026, 10, 5), period_end=date(2026, 10, 11))
        generate_payslips(run)
        slip = run.payslips.get()
        self.assertEqual(slip.advance_recovery, D("1000.00"))
        self.assertEqual(slip.net_pay, D("4000.00"))
        adv.refresh_from_db()
        self.assertEqual(adv.recovered_amount, D("0"))  # nothing applied until finalized
        finalize_run(run)
        adv.refresh_from_db()
        self.assertEqual(adv.recovered_amount, D("1000"))
        self.assertEqual(run.status, PayrollRun.Status.FINALIZED)

    def test_advance_never_makes_net_negative(self):
        SalaryAdvance.objects.create(employee=self.emp, date=date(2026, 10, 1), amount=D("9000"))
        r = calculate_salary(self.emp, date(2026, 10, 5), date(2026, 10, 11))
        self.assertEqual(r.advance_recovery, D("5000.00"))
        self.assertEqual(r.net_pay, D("0.00"))

    def test_finalized_run_cannot_be_regenerated(self):
        run = PayrollRun.objects.create(period_start=date(2026, 10, 5), period_end=date(2026, 10, 11))
        generate_payslips(run)
        finalize_run(run)
        with self.assertRaises(ValueError):
            generate_payslips(run)
