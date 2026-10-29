from django.urls import path

from . import views

app_name = "sharing"

urlpatterns = [
    path("<str:doc_type>/<int:pk>/", views.share, name="share"),
    path("<str:doc_type>/<int:pk>/pdf/", views.share_pdf, name="share_pdf"),
    path("link/<int:link_pk>/stop/", views.revoke, name="revoke"),
]
