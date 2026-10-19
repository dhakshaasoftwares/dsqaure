from django.conf import settings
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("employees/", include("apps.employees.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("admin/", admin.site.urls),
    # PWA files must be served from the site root so they cover every page.
    path("manifest.webmanifest", TemplateView.as_view(
        template_name="pwa/manifest.webmanifest", content_type="application/manifest+json")),
    path("sw.js", TemplateView.as_view(template_name="pwa/sw.js", content_type="application/javascript")),
    path("offline/", TemplateView.as_view(template_name="pwa/offline.html"), name="offline"),
    # Uploaded photos / documents: only for logged-in users. Fine for a small
    # self-hosted install; put them behind nginx / object storage when you grow.
    re_path(r"^media/(?P<path>.*)$", login_required(serve), {"document_root": settings.MEDIA_ROOT}),
]
