from django.urls import path

from . import views

app_name = "payroll"

urlpatterns = [
    path("", views.RunList.as_view(), name="run_list"),
    path("new/", views.RunCreate.as_view(), name="run_create"),
    path("<int:pk>/", views.run_detail, name="run_detail"),
    path("<int:pk>/action/", views.run_action, name="run_action"),
    path("<int:pk>/export/", views.run_export, name="run_export"),
    path("payslip/<int:pk>/", views.payslip_detail, name="payslip"),
    path("my/", views.my_payslips, name="my_payslips"),
    path("advances/", views.AdvanceList.as_view(), name="advance_list"),
    path("advances/new/", views.AdvanceCreate.as_view(), name="advance_create"),
    path("rules/", views.ComponentList.as_view(), name="component_list"),
    path("rules/new/", views.ComponentCreate.as_view(), name="component_create"),
    path("rules/<int:pk>/", views.ComponentUpdate.as_view(), name="component_update"),
]
