import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.attendance import services
from apps.attendance.models import Attendance
from apps.flows.models import Group
from apps.interns.models import Intern


def _period(request) -> tuple[int, int]:
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        datetime.date(year, month, 1)
    except (TypeError, ValueError):
        raise Http404('Некорректный период')
    return year, month


@login_required
def group_sheet(request, pk):
    """Табель группы за месяц."""
    group = get_object_or_404(
        Group.objects.select_related('flow', 'project'), pk=pk,
    )
    year, month = _period(request)
    sheet = services.build_sheet(group, year, month)

    current = datetime.date(year, month, 1)
    prev_month = (current - datetime.timedelta(days=1)).replace(day=1)
    next_month = (current + datetime.timedelta(days=32)).replace(day=1)

    return render(request, 'attendance/group_sheet.html', {
        'group': group,
        'sheet': sheet,
        'year': year,
        'month': month,
        'current': current,
        'prev_month': prev_month,
        'next_month': next_month,
        'today': timezone.localdate(),
        'statuses': Attendance.Status.choices,
    })


@login_required
def toggle(request, pk):
    """AJAX: клик по ячейке табеля переключает отметку."""
    group = get_object_or_404(Group, pk=pk)
    if request.method != 'POST':
        raise Http404
    intern = get_object_or_404(Intern, pk=request.POST.get('intern'))
    try:
        date = datetime.date.fromisoformat(request.POST.get('date', ''))
    except ValueError:
        raise Http404('Некорректная дата')

    mark = services.toggle_mark(group, intern, date, user=request.user)
    return render(request, 'attendance/partials/cell.html', {
        'group': group,
        'intern': intern,
        'cell': {
            'date': date,
            'day': date.day,
            'is_weekend': date.weekday() >= 5,
            'is_today': date == timezone.localdate(),
            'status': mark.status if mark else '',
        },
    })


@login_required
def mark_day(request, pk):
    """Отметить всю группу присутствующей за выбранный день."""
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        try:
            date = datetime.date.fromisoformat(
                request.POST.get('date') or timezone.localdate().isoformat(),
            )
        except ValueError:
            date = timezone.localdate()
        created = services.mark_all_present(group, date, user=request.user)
        messages.success(
            request, f'Отмечено присутствующих: {created} на {date:%d.%m.%Y}.',
        )
    return redirect('attendance:group_sheet', pk=group.pk)
