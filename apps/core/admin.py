from django.contrib import admin

from .models import CompanySettings, Project

admin.site.register(CompanySettings)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "client_name", "status", "start_date"]
    list_filter = ["status"]
    search_fields = ["code", "name", "client_name"]
