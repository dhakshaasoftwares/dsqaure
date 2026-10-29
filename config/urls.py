from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from apps.core.views import protected_media
from apps.sharing.views import public as sharing_public

urlpatterns = [
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("employees/", include("apps.employees.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("payroll/", include("apps.payroll.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("progress/", include("apps.progress.urls")),
    path("documents/", include("apps.documents.urls")),
    path("billing/", include("apps.billing.urls")),
    path("licence/", include("apps.licensing.urls")),
    path("send/", include("apps.sharing.urls")),
    path("s/<str:token>/", sharing_public, name="share_public"),
    path("admin/", admin.site.urls),
    # PWA files must be served from the site root so they cover every page.
    path("manifest.webmanifest", TemplateView.as_view(
        template_name="pwa/manifest.webmanifest", content_type="application/manifest+json")),
    path("sw.js", TemplateView.as_view(template_name="pwa/sw.js", content_type="application/javascript")),
    path("offline/", TemplateView.as_view(template_name="pwa/offline.html"), name="offline"),
    # Uploaded photos / documents are only shown to users whose role allows it.
    re_path(r"^media/(?P<path>.*)$", protected_media),
]
