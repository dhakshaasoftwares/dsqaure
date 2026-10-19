from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path("me/", views.my_attendance, name="me"),
    path("mark/", views.mark_attendance, name="mark"),
    path("register/", views.register, name="register"),
]
