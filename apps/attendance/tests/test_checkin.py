import tempfile
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import Attendance
from apps.attendance.services import CheckInError, distance_m, self_check_in, self_check_out
from apps.core.models import CompanySettings, Project
from apps.employees.models import Employee

# 1x1 transparent GIF
PHOTO = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
         b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def photo():
    return SimpleUploadedFile("selfie.gif", PHOTO, content_type="image/gif")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class CheckInTests(TestCase):
    def setUp(self):
        self.site = Project.objects.create(name="Anna Nagar Villa", code="ANV",
                                           latitude=Decimal("13.085000"), longitude=Decimal("80.210000"),
                                           geofence_radius_m=200)
        self.user = User.objects.create_user("worker", password="x")
        self.emp = Employee.objects.create(code="W1", name="Worker", user=self.user, default_project=self.site,
                                           wage_rate=Decimal("700"))

    def test_distance(self):
        # ~111 m per 0.001 degree of latitude
        self.assertAlmostEqual(distance_m(13.085, 80.21, 13.086, 80.21), 111, delta=2)

    def test_check_in_inside_radius(self):
        rec = self_check_in(self.emp, self.site, "13.085500", "80.210000", photo(), self.user)
        self.assertEqual(rec.status, Attendance.Status.PRESENT)
        self.assertLess(rec.check_in_distance_m, 200)
        self.assertTrue(rec.check_in_photo)

    def test_check_in_outside_radius_rejected(self):
        with self.assertRaises(CheckInError):
            self_check_in(self.emp, self.site, "13.100000", "80.210000", photo(), self.user)
        self.assertFalse(Attendance.objects.exists())

    def test_geofence_can_be_switched_off(self):
        company = CompanySettings.load()
        company.attendance_geofence_required = False
        company.save()
        self_check_in(self.emp, self.site, "13.100000", "80.210000", photo(), self.user)
        self.assertEqual(Attendance.objects.count(), 1)

    def test_photo_required(self):
        with self.assertRaises(CheckInError):
            self_check_in(self.emp, self.site, "13.085500", "80.210000", None, self.user)

    def test_double_check_in_rejected(self):
        self_check_in(self.emp, self.site, "13.085500", "80.210000", photo(), self.user)
        with self.assertRaises(CheckInError):
            self_check_in(self.emp, self.site, "13.085500", "80.210000", photo(), self.user)

    def test_check_out_records_overtime(self):
        rec = self_check_in(self.emp, self.site, "13.085500", "80.210000", photo(), self.user)
        rec.check_in_at = timezone.now() - timezone.timedelta(hours=10, minutes=40)
        rec.save()
        rec = self_check_out(self.emp)
        self.assertEqual(rec.overtime_hours, Decimal("2.5"))


class MarkAttendanceViewTests(TestCase):
    def setUp(self):
        self.site = Project.objects.create(name="Site", code="S1")
        self.emp1 = Employee.objects.create(code="A", name="A", default_project=self.site)
        self.emp2 = Employee.objects.create(code="B", name="B", default_project=self.site)
        supervisor_role = Group.objects.create(name="Supervisor")
        from django.contrib.auth.models import Permission
        supervisor_role.permissions.set(Permission.objects.filter(
            codename__in=["add_attendance", "change_attendance", "view_attendance"]))
        self.sup = User.objects.create_user("sup", password="x")
        self.sup.groups.add(supervisor_role)

    def test_supervisor_marks_whole_site(self):
        self.client.force_login(self.sup)
        today = timezone.localdate().isoformat()
        resp = self.client.post(reverse("attendance:mark"), {
            "date": today, "project": self.site.pk,
            f"status_{self.emp1.pk}": "present", f"ot_{self.emp1.pk}": "2",
            f"status_{self.emp2.pk}": "absent",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Attendance.objects.get(employee=self.emp1).overtime_hours, Decimal("2"))
        self.assertEqual(Attendance.objects.get(employee=self.emp2).status, "absent")

    def test_invalid_status_ignored(self):
        self.client.force_login(self.sup)
        self.client.post(reverse("attendance:mark"), {
            "date": timezone.localdate().isoformat(), "project": self.site.pk,
            f"status_{self.emp1.pk}": "bogus",
        })
        self.assertFalse(Attendance.objects.exists())

    def test_user_without_permission_is_blocked(self):
        nobody = User.objects.create_user("nobody", password="x")
        self.client.force_login(nobody)
        self.assertEqual(self.client.get(reverse("attendance:mark")).status_code, 403)
