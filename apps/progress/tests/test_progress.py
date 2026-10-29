import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.accounts.models import User
from apps.core.models import Project
from apps.core.setup import ensure_masters
from apps.progress.models import ProgressPhoto, ProjectStage, StageTemplate
from apps.progress.services import apply_standard_stages, overall_percent, record_update

D = Decimal


def big_photo():
    buf = BytesIO()
    Image.new("RGB", (4000, 3000), "orange").save(buf, "PNG")
    return SimpleUploadedFile("site.png", buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProgressTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Villa", code="V1")
        self.user = User.objects.create_superuser("owner", password="x")

    def test_overall_is_weighted(self):
        ProjectStage.objects.create(project=self.project, name="Foundation", weight=D("10"), percent=D("100"))
        ProjectStage.objects.create(project=self.project, name="Painting", weight=D("30"), percent=D("0"))
        self.assertEqual(overall_percent(self.project), D("25.0"))

    def test_no_stages_means_no_percent(self):
        self.assertIsNone(overall_percent(self.project))

    def test_standard_stages_copied_once(self):
        ensure_masters()
        count = StageTemplate.objects.filter(is_active=True).count()
        self.assertEqual(apply_standard_stages(self.project), count)
        self.assertEqual(apply_standard_stages(self.project), 0)
        self.assertEqual(self.project.stages.count(), count)

    def test_update_sets_stage_dates_and_shrinks_photo(self):
        stage = ProjectStage.objects.create(project=self.project, name="Slab", weight=D("1"))
        day = date(2026, 10, 1)
        record_update(self.project, stage, day, D("40"), "Shuttering done", [big_photo()], self.user)
        stage.refresh_from_db()
        self.assertEqual(stage.percent, D("40"))
        self.assertEqual(stage.actual_start, day)
        self.assertIsNone(stage.actual_end)
        photo = ProgressPhoto.objects.get()
        with Image.open(photo.image.path) as img:
            self.assertLessEqual(max(img.size), 1600)
        record_update(self.project, stage, day + timedelta(days=5), D("100"), "", [], self.user)
        stage.refresh_from_db()
        self.assertEqual(stage.actual_end, day + timedelta(days=5))

    def test_delayed_state(self):
        stage = ProjectStage.objects.create(project=self.project, name="Slab", percent=D("50"),
                                            planned_end=timezone.localdate() - timedelta(days=1))
        self.assertEqual(stage.state, ProjectStage.State.DELAYED)

    def test_screens(self):
        self.client.force_login(self.user)
        ensure_masters()
        resp = self.client.post(f"/progress/project/{self.project.pk}/standard-stages/")
        self.assertEqual(resp.status_code, 302)
        stage = self.project.stages.first()
        resp = self.client.post(f"/progress/project/{self.project.pk}/", {
            "stage": stage.pk, "percent": "30", "date": "2026-10-29", "note": "Started", "photos": [big_photo()],
        })
        self.assertEqual(resp.status_code, 302)
        stage.refresh_from_db()
        self.assertEqual(stage.percent, D("30"))
        for url in ["/progress/", f"/progress/project/{self.project.pk}/", f"/progress/project/{self.project.pk}/photos/",
                    f"/progress/project/{self.project.pk}/stage/new/",
                    f"/progress/project/{self.project.pk}/stage/{stage.pk}/", "/progress/stages/",
                    f"/projects/{self.project.pk}/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        report = self.client.get(f"/progress/project/{self.project.pk}/report/")
        self.assertEqual(report.status_code, 200)
        self.assertIn(report["Content-Type"], ("application/pdf", "text/html; charset=utf-8"))

    def test_update_needs_something(self):
        self.client.force_login(self.user)
        resp = self.client.post(f"/progress/project/{self.project.pk}/", {"date": "2026-10-29"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(self.project.progress_updates.exists())
