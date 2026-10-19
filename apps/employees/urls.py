from django.urls import path

from . import views

app_name = "employees"

urlpatterns = [
    path("", views.EmployeeList.as_view(), name="list"),
    path("new/", views.EmployeeCreate.as_view(), name="create"),
    path("<int:pk>/", views.EmployeeDetail.as_view(), name="detail"),
    path("<int:pk>/edit/", views.EmployeeUpdate.as_view(), name="update"),
]
