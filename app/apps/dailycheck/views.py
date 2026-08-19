import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.dailycheck.models import (
    ProjectCheckItem,
    ProjectCheckMark,
    ensure_project_items,
)


def _day(request) -> datetime.date:
    raw = request.GET.get('date', '')
    if not raw:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        raise Http404('Некорректная дата')


def _day_from_post(request) -> datetime.date:
    try:
        return datetime.date.fromisoformat(request.POST.get('date', ''))
    except ValueError:
        return timezone.localdate()


def project_rows(project, day: datetime.date) -> list[dict]:
    """Пункты ежедневной проверки проекта за день."""
    ensure_project_items(project)
    items = list(ProjectCheckItem.objects.filter(
        project=project, is_active=True,
    ))
    marks = {
        mark.item_id: mark
        for mark in ProjectCheckMark.objects.filter(
            date=day, item__project=project,
        ).select_related('checked_by')
    }
    rows = []
    for item in items:
        mark = marks.get(item.pk)
        rows.append({
            'item': item,
            'date': day,
            'mark': mark,
            'is_done': bool(mark and mark.is_done),
            'note': mark.note if mark else '',
        })
    return rows


@login_required
def project_toggle(request, pk):
    """AJAX: отметка по ежедневному пункту проекта."""
    if request.method != 'POST':
        raise Http404
    item = get_object_or_404(ProjectCheckItem, pk=pk)
    day = _day_from_post(request)

    mark = ProjectCheckMark.objects.filter(date=day, item=item).first()
    if mark and mark.is_done:
        mark.delete()
        mark = None
    else:
        mark = ProjectCheckMark.objects.create(
            date=day, item=item, is_done=True, checked_by=request.user,
        )
    return render(request, 'dailycheck/partials/project_row.html', {
        'row': {
            'item': item, 'date': day, 'mark': mark,
            'is_done': bool(mark), 'note': mark.note if mark else '',
        },
    })


@login_required
def project_note(request, pk):
    """AJAX: заметка по пункту проекта."""
    if request.method != 'POST':
        raise Http404
    item = get_object_or_404(ProjectCheckItem, pk=pk)
    day = _day_from_post(request)
    text = request.POST.get('note', '').strip()[:255]

    mark = ProjectCheckMark.objects.filter(date=day, item=item).first()
    if mark:
        mark.note = text
        mark.checked_by = request.user
        mark.save(update_fields=['note', 'checked_by', 'updated_at'])
    elif text:
        mark = ProjectCheckMark.objects.create(
            date=day, item=item, is_done=False, note=text,
            checked_by=request.user,
        )
    return render(request, 'dailycheck/partials/project_row.html', {
        'row': {
            'item': item, 'date': day, 'mark': mark,
            'is_done': bool(mark and mark.is_done),
            'note': mark.note if mark else '',
        },
    })


@login_required
def project_item_create(request, pk):
    """Добавить свой ежедневный пункт в проект."""
    from apps.projects.models import Project

    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        if title:
            ProjectCheckItem.objects.create(
                project=project, title=title,
                hint=request.POST.get('hint', '').strip()[:255],
                order=(ProjectCheckItem.objects.filter(
                    project=project,
                ).count() + 1) * 10,
            )
            messages.success(request, f'Пункт «{title}» добавлен.')
        else:
            messages.error(request, 'Напишите, что проверять.')
    return redirect(f'{project.get_absolute_url()}?tab=daily')


@login_required
def project_item_delete(request, pk):
    """Убрать пункт из ежедневной проверки проекта."""
    item = get_object_or_404(
        ProjectCheckItem.objects.select_related('project'), pk=pk,
    )
    project = item.project
    if request.method == 'POST':
        item.is_active = False
        item.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Пункт «{item.title}» убран.')
    return redirect(f'{project.get_absolute_url()}?tab=daily')
