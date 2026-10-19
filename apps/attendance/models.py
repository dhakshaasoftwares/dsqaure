from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Attendance(models.Model):
    """One row per employee per day."""

    class Status(models.TextChoices):
        PRESENT = "present", _("Present")
        HALF_DAY = "half_day", _("Half day")
        ABSENT = "absent", _("Absent")
        LEAVE = "leave", _("Leave")
        WEEK_OFF = "week_off", _("Weekly off")
        HOLIDAY = "holiday", _("Holiday")

    class Source(models.TextChoices):
        SELF = "self", _("Self check-in")
        SUPERVISOR = "supervisor", _("Marked by supervisor")

    # Fraction of a day each status counts as, for wage calculation.
    DAY_VALUE = {
        Status.PRESENT: Decimal("1"),
        Status.HALF_DAY: Decimal("0.5"),
    }

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="attendance", verbose_name=_("employee")
    )
    date = models.DateField(_("date"), db_index=True)
    project = models.ForeignKey(
        "core.Project", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="attendance", verbose_name=_("site"),
    )
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.PRESENT)
    overtime_hours = models.DecimalField(_("overtime hours"), max_digits=4, decimal_places=2, default=0)

    check_in_at = models.DateTimeField(_("check-in time"), null=True, blank=True)
    check_out_at = models.DateTimeField(_("check-out time"), null=True, blank=True)
    check_in_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_distance_m = models.PositiveIntegerField(_("distance from site (m)"), null=True, blank=True)
    check_in_photo = models.ImageField(_("check-in photo"), upload_to="attendance/%Y/%m/", blank=True)

    source = models.CharField(_("source"), max_length=12, choices=Source.choices, default=Source.SUPERVISOR)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "employee__name"]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="one_attendance_per_employee_per_day")
        ]
        verbose_name = _("attendance")
        verbose_name_plural = _("attendance")

    def __str__(self):
        return f"{self.employee} {self.date} {self.get_status_display()}"

    @property
    def day_value(self):
        return self.DAY_VALUE.get(self.status, Decimal("0"))
