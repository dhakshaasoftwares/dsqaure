from .models import Location


def sync_site_location(sender, instance, raw=False, **kwargs):
    """Every project automatically gets a stock location with the same name."""
    if raw:
        return
    location, created = Location.objects.get_or_create(
        project=instance, defaults={"name": instance.name, "kind": Location.Kind.SITE})
    if not created and location.name != instance.name:
        location.name = instance.name
        location.save(update_fields=["name"])
