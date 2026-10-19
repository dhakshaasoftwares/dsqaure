from django.contrib import admin

from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ["date", "employee", "project", "status", "overtime_hours", "source"]
    list_filter = ["status", "source", "project", "date"]
    search_fields = ["employee__name", "employee__code"]
    date_hierarchy = "date"
