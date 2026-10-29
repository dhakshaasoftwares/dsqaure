from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.core.audit import track
        from apps.core.models import Project

        from . import models as m
        from .signals import sync_site_location

        post_save.connect(sync_site_location, sender=Project, dispatch_uid="inventory-site-location")
        track(m.Material, m.Supplier, m.Location, m.PurchaseOrder, m.GoodsReceipt, m.StockTransfer,
              m.MaterialIssue, m.StockAdjustment)
