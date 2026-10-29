from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.images import compress_image

from .models import ProgressPhoto, ProgressUpdate, ProjectStage, StageTemplate

ZERO = Decimal("0")


def _weighted(stages):
    total_weight = sum((s.weight for s in stages), ZERO)
    if not total_weight:
        return None
    done = sum((s.weight * s.percent for s in stages), ZERO)
    return (done / total_weight).quantize(Decimal("0.1"))


def overall_percent(project):
    """Overall completion = stage % weighted by each stage's share of the job."""
    return _weighted(list(project.stages.all()))


def overall_percent_map(projects):
    by_project = defaultdict(list)
    for stage in ProjectStage.objects.filter(project__in=list(projects)):
        by_project[stage.project_id].append(stage)
    return {pid: _weighted(stages) for pid, stages in by_project.items()}


@transaction.atomic
def apply_standard_stages(project):
    """Copy the company's standard stages into a project (only stages it does not have yet)."""
    existing = set(project.stages.values_list("name", flat=True))
    start = project.stages.count()
    added = 0
    for template in StageTemplate.objects.filter(is_active=True):
        if template.name in existing:
            continue
        ProjectStage.objects.create(project=project, name=template.name, order=start + template.order,
                                    weight=template.weight)
        added += 1
    return added


@transaction.atomic
def record_update(project, stage, date, percent, note, photos, user, caption=""):
    update = ProgressUpdate.objects.create(project=project, stage=stage, date=date, percent=percent, note=note,
                                           created_by=user)
    if stage and percent is not None:
        stage.percent = percent
        if percent > 0 and not stage.actual_start:
            stage.actual_start = date
        if percent >= 100 and not stage.actual_end:
            stage.actual_end = date
        if percent < 100:
            stage.actual_end = None
        stage.save()
    for photo in photos:
        ProgressPhoto.objects.create(project=project, stage=stage, update=update, image=compress_image(photo),
                                     caption=caption or (note[:200] if note else ""), taken_on=date or
                                     timezone.localdate(), uploaded_by=user)
    return update
