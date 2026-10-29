from django.urls import path

from . import views
from .crud import Crud
from .models import Unit

app_name = "core"

units = Crud(Unit, "unit", fields=["name", "symbol"], columns=["name", "symbol"], search=["name", "symbol"])

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("setup/", views.setup, name="setup"),
    path("menu/", views.menu, name="menu"),
    path("projects/", views.ProjectList.as_view(), name="project_list"),
    path("projects/new/", views.ProjectCreate.as_view(), name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.ProjectUpdate.as_view(), name="project_update"),
    path("settings/", views.SettingsUpdate.as_view(), name="settings"),
    path("configuration/", views.configuration, name="configuration"),
    path("configuration/numbering/", views.NumberSequenceList.as_view(), name="number_series"),
    path("configuration/numbering/<int:pk>/", views.NumberSequenceUpdate.as_view(), name="number_series_update"),
    path("audit/", views.AuditLogList.as_view(), name="audit_log"),
    *units.urls("configuration/units/"),
]
