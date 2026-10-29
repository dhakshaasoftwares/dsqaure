import math
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.images import compress_image
from apps.core.models import CompanySettings

from .models import Attendance


class CheckInError(Exception):
    pass


def distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres (haversine)."""
    lat1, lng1, lat2, lng2 = map(lambda v: math.radians(float(v)), (lat1, lng1, lat2, lng2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


def self_check_in(employee, project, lat, lng, photo, user):
    company = CompanySettings.load()
    today = timezone.localdate()

    if Attendance.objects.filter(employee=employee, date=today, check_in_at__isnull=False).exists():
        raise CheckInError(_("You have already checked in today."))
    if company.attendance_selfie_required and not photo:
        raise CheckInError(_("Please take a photo to check in."))

    distance = None
    if lat not in (None, "") and lng not in (None, "") and project and project.has_location:
        distance = round(distance_m(lat, lng, project.latitude, project.longitude))
    if company.attendance_geofence_required and project and project.has_location:
        if distance is None:
            raise CheckInError(_("Location is required. Please allow location access and try again."))
        if distance > project.geofence_radius_m:
            raise CheckInError(
                _("You are %(d)s m away from the site. Check-in is allowed within %(r)s m.")
                % {"d": distance, "r": project.geofence_radius_m}
            )

    record, _created = Attendance.objects.update_or_create(
        employee=employee,
        date=today,
        defaults={
            "project": project,
            "status": Attendance.Status.PRESENT,
            "check_in_at": timezone.now(),
            "check_in_lat": Decimal(str(lat)).quantize(Decimal("0.000001")) if lat not in (None, "") else None,
            "check_in_lng": Decimal(str(lng)).quantize(Decimal("0.000001")) if lng not in (None, "") else None,
            "check_in_distance_m": distance,
            "source": Attendance.Source.SELF,
            "marked_by": user,
        },
    )
    if photo:
        record.check_in_photo = compress_image(photo)
        record.save(update_fields=["check_in_photo"])
    return record


def self_check_out(employee):
    today = timezone.localdate()
    record = Attendance.objects.filter(employee=employee, date=today, check_in_at__isnull=False).first()
    if record is None:
        raise CheckInError(_("You have not checked in today."))
    if record.check_out_at:
        raise CheckInError(_("You have already checked out today."))
    record.check_out_at = timezone.now()
    company = CompanySettings.load()
    worked_hours = Decimal((record.check_out_at - record.check_in_at).total_seconds() / 3600)
    extra = worked_hours - company.working_hours_per_day
    if extra > 0:
        # Overtime counted in half-hour steps.
        record.overtime_hours = (extra * 2).quantize(Decimal("1"), rounding="ROUND_DOWN") / 2
    record.save(update_fields=["check_out_at", "overtime_hours"])
    return record
