from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("menu/", views.menu, name="menu"),
    path("projects/", views.ProjectList.as_view(), name="project_list"),
    path("projects/new/", views.ProjectCreate.as_view(), name="project_create"),
    path("projects/<int:pk>/", views.ProjectUpdate.as_view(), name="project_update"),
    path("settings/", views.SettingsUpdate.as_view(), name="settings"),
]
