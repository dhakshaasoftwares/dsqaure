from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password/", auth_views.PasswordChangeView.as_view(
        template_name="form.html", success_url=reverse_lazy("core:dashboard"), extra_context={"title": _("Change password")}),
        name="password_change"),
    path("language/", views.SetLanguage.as_view(), name="set_language"),
    path("users/", views.UserList.as_view(), name="user_list"),
    path("users/new/", views.UserCreate.as_view(), name="user_create"),
    path("users/<int:pk>/", views.UserUpdate.as_view(), name="user_update"),
    path("roles/", views.RoleList.as_view(), name="role_list"),
    path("roles/new/", views.RoleCreate.as_view(), name="role_create"),
    path("roles/<int:pk>/", views.RoleUpdate.as_view(), name="role_update"),
]
