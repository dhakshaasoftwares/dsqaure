import calendar
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.core.models import Project
from apps.employees.models import Employee

from .models import Attendance
from .services import CheckInError, self_check_in, self_check_out


@login_required
def my_attendance(request):
    employee = getattr(request.user, "employee", None)
    if employee is None:
        messages.warning(request, _("Your login is not linked to an employee record. Ask the admin to link it."))
        return redirect("core:dashboard")

    if request.method == "POST":
        try:
            if request.POST.get("action") == "check_out":
                self_check_out(employee)
                messages.success(request, _("Checked out. Have a good evening!"))
            else:
                project = Project.objects.filter(pk=request.POST.get("project") or None).first()
                self_check_in(
                    employee, project or employee.default_project,
                    request.POST.get("lat"), request.POST.get("lng"),
                    request.FILES.get("photo"), request.user,
                )
                messages.success(request, _("Checked in successfully."))
        except CheckInError as exc:
            messages.error(request, str(exc))
        return redirect("attendance:me")

    today = timezone.localdate()
    return render(request, "attendance/me.html", {
        "employee": employee,
        "today_record": Attendance.objects.filter(employee=employee, date=today).first(),
        "recent": employee.attendance.select_related("project")[:10],
        "projects": Project.objects.filter(status=Project.Status.ACTIVE),
    })


@login_required
@permission_required(["attendance.add_attendance", "attendance.change_attendance"], raise_exception=True)
def mark_attendance(request):
    """Supervisor marks a whole site in one screen (for workers without smartphones)."""
    day = parse_date(request.GET.get("date") or request.POST.get("date") or "") or timezone.localdate()
    projects = Project.objects.filter(status=Project.Status.ACTIVE)
    project_id = request.GET.get("project") or request.POST.get("project")
    project = projects.filter(pk=project_id).first() if project_id else projects.first()

    existing = {a.employee_id: a for a in Attendance.objects.filter(date=day)}
    employees = Employee.objects.filter(is_active=True)
    if project:
        employees = employees.filter(
            Q(default_project=project) | Q(pk__in=[e for e, a in existing.items() if a.project_id == project.pk])
        )

    if request.method == "POST":
        saved = 0
        with transaction.atomic():
            for emp in employees:
                status = request.POST.get(f"status_{emp.pk}")
                if status not in Attendance.Status.values and status != "clear":
                    continue
                if status == "clear":
                    Attendance.objects.filter(employee=emp, date=day).delete()
                    continue
                try:
                    ot = Decimal(request.POST.get(f"ot_{emp.pk}") or "0")
                except InvalidOperation:
                    ot = Decimal("0")
                Attendance.objects.update_or_create(
                    employee=emp, date=day,
                    defaults={"status": status, "overtime_hours": ot, "project": project,
                              "marked_by": request.user,
                              "notes": request.POST.get(f"note_{emp.pk}", "")[:255]},
                )
                saved += 1
        messages.success(request, _("Attendance saved for %(n)s people.") % {"n": saved})
        return redirect(f"{request.path}?date={day.isoformat()}&project={project.pk if project else ''}")

    rows = [{"employee": e, "record": existing.get(e.pk)} for e in employees]
    return render(request, "attendance/mark.html", {
        "day": day, "projects": projects, "project": project, "rows": rows,
        "statuses": Attendance.Status.choices,
    })


@login_required
@permission_required("attendance.view_attendance", raise_exception=True)
def register(request):
    """Monthly muster roll: employees down, days across."""
    today = timezone.localdate()
    try:
        year, month = map(int, (request.GET.get("month") or today.strftime("%Y-%m")).split("-"))
        first = date(year, month, 1)
    except ValueError:
        first = today.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    project = Project.objects.filter(pk=request.GET.get("project") or None).first()

    records = Attendance.objects.filter(date__range=(first, last)).select_related("employee")
    if project:
        records = records.filter(project=project)
    short = {"present": "P", "half_day": "½", "absent": "A", "leave": "L", "week_off": "WO", "holiday": "H"}
    grid = {}
    for rec in records:
        row = grid.setdefault(rec.employee, {"days": {}, "total": Decimal("0"), "ot": Decimal("0")})
        row["days"][rec.date.day] = short.get(rec.status, "")
        row["total"] += rec.day_value
        row["ot"] += rec.overtime_hours
    days = list(range(1, last.day + 1))
    table = [
        {"employee": emp, "cells": [data["days"].get(d, "") for d in days], "total": data["total"], "ot": data["ot"]}
        for emp, data in sorted(grid.items(), key=lambda kv: kv[0].name)
    ]
    return render(request, "attendance/register.html", {
        "month": first, "days": days, "table": table, "project": project,
        "projects": Project.objects.all(),
    })
