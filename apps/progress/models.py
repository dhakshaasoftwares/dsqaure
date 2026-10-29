from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

PERCENT = [MinValueValidator(0), MaxValueValidator(100)]


class StageTemplate(models.Model):
    """The company's standard list of construction stages, copied into each new project."""

    name = models.CharField(_("stage"), max_length=150)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    weight = models.DecimalField(_("weight"), max_digits=6, decimal_places=2, default=Decimal("1"),
                                 help_text=_("How much of the whole job this stage is, e.g. slab 12, painting 8"))
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = _("standard stage")
        verbose_name_plural = _("standard stages")

    def __str__(self):
        return self.name


class ProjectStage(models.Model):
    class State(models.TextChoices):
        NOT_STARTED = "not_started", _("Not started")
        IN_PROGRESS = "in_progress", _("In progress")
        DELAYED = "delayed", _("Delayed")
        DONE = "done", _("Completed")

    project = models.ForeignKey("core.Project", on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(_("stage"), max_length=150)
    order = models.PositiveSmallIntegerField(_("order"), default=0)
    weight = models.DecimalField(_("weight"), max_digits=6, decimal_places=2, default=Decimal("1"))
    planned_start = models.DateField(_("planned start"), null=True, blank=True)
    planned_end = models.DateField(_("planned finish"), null=True, blank=True)
    actual_start = models.DateField(_("actual start"), null=True, blank=True)
    actual_end = models.DateField(_("actual finish"), null=True, blank=True)
    percent = models.DecimalField(_("complete (%)"), max_digits=5, decimal_places=2, default=0, validators=PERCENT)
    notes = models.TextField(_("notes"), blank=True)

    class Meta:
        ordering = ["project", "order", "pk"]
        verbose_name = _("project stage")
        verbose_name_plural = _("project stages")

    def __str__(self):
        return f"{self.project.name} – {self.name}"

    @property
    def state(self):
        if self.percent >= 100:
            return self.State.DONE
        if self.planned_end and self.planned_end < timezone.localdate():
            return self.State.DELAYED
        if self.percent > 0:
            return self.State.IN_PROGRESS
        return self.State.NOT_STARTED

    @property
    def state_label(self):
        return self.State(self.state).label


class ProgressUpdate(models.Model):
    project = models.ForeignKey("core.Project", on_delete=models.CASCADE, related_name="progress_updates")
    stage = models.ForeignKey(ProjectStage, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="updates", verbose_name=_("stage"))
    date = models.DateField(_("date"), default=timezone.localdate)
    percent = models.DecimalField(_("stage now complete (%)"), max_digits=5, decimal_places=2, null=True,
                                  blank=True, validators=PERCENT)
    note = models.TextField(_("what was done"), blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        verbose_name = _("progress update")
        verbose_name_plural = _("progress updates")

    def __str__(self):
        return f"{self.project.name} {self.date}"


class ProgressPhoto(models.Model):
    project = models.ForeignKey("core.Project", on_delete=models.CASCADE, related_name="photos")
    stage = models.ForeignKey(ProjectStage, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="photos", verbose_name=_("stage"))
    update = models.ForeignKey(ProgressUpdate, on_delete=models.CASCADE, null=True, blank=True,
                               related_name="photos")
    image = models.ImageField(_("photo"), upload_to="progress/%Y/%m/")
    caption = models.CharField(_("caption"), max_length=200, blank=True)
    taken_on = models.DateField(_("date"), default=timezone.localdate)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name="+")

    class Meta:
        ordering = ["-taken_on", "-pk"]
        verbose_name = _("site photo")
        verbose_name_plural = _("site photos")

    def __str__(self):
        return self.caption or self.image.name
