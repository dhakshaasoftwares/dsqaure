from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.models import Project
from apps.core.pdf import pdf_response

from .forms import ProgressUpdateForm, ProjectStageForm
from .models import ProgressPhoto, ProjectStage
from .services import apply_standard_stages, overall_percent, overall_percent_map, record_update


@login_required
@permission_required("progress.view_projectstage", raise_exception=True)
def overview(request):
    show_all = request.GET.get("show") == "all"
    projects = Project.objects.all() if show_all else Project.objects.exclude(status=Project.Status.COMPLETED)
    projects = list(projects.prefetch_related("stages"))
    pct = overall_percent_map(projects)
    for p in projects:
        p.progress = pct.get(p.pk)
        p.delayed = sum(1 for s in p.stages.all() if s.state == ProjectStage.State.DELAYED)
    return render(request, "progress/overview.html", {"projects": projects, "show_all": show_all})


@login_required
@permission_required("progress.view_projectstage", raise_exception=True)
def project_progress(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = ProgressUpdateForm(request.POST or None, request.FILES or None, project=project)
    if request.method == "POST":
        if not request.user.has_perm("progress.add_progressupdate"):
            messages.error(request, _("Your role cannot add progress updates."))
        elif form.is_valid():
            d = form.cleaned_data
            record_update(project, d["stage"], d["date"], d["percent"], d["note"], d["photos"], request.user)
            messages.success(request, _("Progress saved."))
            return redirect("progress:project", pk=pk)
    return render(request, "progress/project.html", {
        "project": project, "form": form, "stages": project.stages.all(), "overall": overall_percent(project),
        "updates": project.progress_updates.select_related("stage", "created_by").prefetch_related("photos")[:15],
    })


@require_POST
@login_required
@permission_required("progress.add_projectstage", raise_exception=True)
def apply_stages(request, pk):
    project = get_object_or_404(Project, pk=pk)
    added = apply_standard_stages(project)
    messages.success(request, _("%(n)s standard stages added.") % {"n": added})
    return redirect("progress:project", pk=pk)


@login_required
def stage_form(request, pk, stage_pk=None):
    project = get_object_or_404(Project, pk=pk)
    stage = get_object_or_404(ProjectStage, pk=stage_pk, project=project) if stage_pk else None
    perm = "progress.change_projectstage" if stage else "progress.add_projectstage"
    if not request.user.has_perm(perm):
        return render(request, "403.html", status=403)
    form = ProjectStageForm(request.POST or None, instance=stage,
                            initial=None if stage else {"order": project.stages.count() + 1})
    if request.method == "POST":
        if request.POST.get("delete") and stage and request.user.has_perm("progress.delete_projectstage"):
            stage.delete()
            messages.success(request, _("Stage deleted."))
            return redirect("progress:project", pk=pk)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.project = project
            obj.save()
            messages.success(request, _("Stage saved."))
            return redirect("progress:project", pk=pk)
    return render(request, "progress/stage_form.html", {"project": project, "stage": stage, "form": form})


@login_required
@permission_required("progress.view_progressphoto", raise_exception=True)
def photos(request, pk):
    project = get_object_or_404(Project, pk=pk)
    qs = project.photos.select_related("stage")
    stage = request.GET.get("stage")
    if stage:
        qs = qs.filter(stage_id=stage)
    page = Paginator(qs, 24).get_page(request.GET.get("page"))
    return render(request, "progress/photos.html", {"project": project, "page_obj": page,
                                                     "stages": project.stages.all(), "stage": stage})


@require_POST
@login_required
@permission_required("progress.delete_progressphoto", raise_exception=True)
def photo_delete(request, photo_pk):
    photo = get_object_or_404(ProgressPhoto, pk=photo_pk)
    project_pk = photo.project_id
    photo.image.delete(save=False)
    photo.delete()
    messages.success(request, _("Photo deleted."))
    return redirect("progress:photos", pk=project_pk)


@login_required
@permission_required("progress.view_projectstage", raise_exception=True)
def report(request, pk):
    """Progress report to share with the client (PDF)."""
    project = get_object_or_404(Project.objects.select_related("client"), pk=pk)
    return pdf_response(request, "progress/report_pdf.html", {
        "project": project, "stages": project.stages.all(), "overall": overall_percent(project),
        "photos": project.photos.all()[:12], "updates": project.progress_updates.select_related("stage")[:10],
    }, f"Progress-{project.code}")
