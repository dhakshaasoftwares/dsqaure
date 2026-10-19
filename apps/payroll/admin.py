from django.contrib import admin

from .models import PayComponent, PayrollRun, Payslip, SalaryAdvance


@admin.register(PayComponent)
class PayComponentAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "method", "value", "applies_to", "apply_to_everyone", "is_active"]


@admin.register(SalaryAdvance)
class SalaryAdvanceAdmin(admin.ModelAdmin):
    list_display = ["employee", "date", "amount", "recovered_amount"]


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0
    fields = ["employee", "paid_days", "gross_pay", "total_deductions", "net_pay"]
    readonly_fields = fields


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ["period_start", "period_end", "wage_type", "project", "status"]
    inlines = [PayslipInline]
