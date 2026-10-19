from django.contrib import admin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "designation", "wage_type", "wage_rate", "default_project", "is_active"]
    list_filter = ["wage_type", "is_active", "default_project"]
    search_fields = ["code", "name", "phone"]
