from django.urls import path
from django.utils.translation import gettext_lazy as _

from apps.core.crud import Crud

from . import views
from .models import StageTemplate

app_name = "progress"

stage_templates = Crud(
    StageTemplate, "stage_template", fields=["name", "order", "weight", "is_active"],
    columns=["order", "name", "weight", "is_active"], search=["name"],
    intro=_("These stages are copied into a project when you press 'Add standard stages'."),
)

urlpatterns = [
    path("", views.overview, name="overview"),
    path("project/<int:pk>/", views.project_progress, name="project"),
    path("project/<int:pk>/standard-stages/", views.apply_stages, name="apply_stages"),
    path("project/<int:pk>/stage/new/", views.stage_form, name="stage_create"),
    path("project/<int:pk>/stage/<int:stage_pk>/", views.stage_form, name="stage_update"),
    path("project/<int:pk>/photos/", views.photos, name="photos"),
    path("project/<int:pk>/report/", views.report, name="report"),
    path("photo/<int:photo_pk>/delete/", views.photo_delete, name="photo_delete"),
    *stage_templates.urls("stages/"),
]
