from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("", views.invoice_list, name="invoice_list"),
    path("new/", views.invoice_create, name="invoice_create"),
    path("<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("<int:pk>/edit/", views.invoice_update, name="invoice_update"),
    path("<int:pk>/action/", views.invoice_action, name="invoice_action"),
    path("<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("<int:pk>/payment/", views.payment_add, name="payment_add"),
    path("payment/<int:pk>/delete/", views.payment_delete, name="payment_delete"),
    path("payments/", views.payment_list, name="payment_list"),
    path("agreement/<int:agreement_pk>/", views.statement, name="statement"),
]
