import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.attendance import overview, services
from apps.attendance.models import GroupMeeting, MeetingKind
from apps.flows.models import Group
from apps.interns.models import Intern


class MeetingCreateForm(forms.Form):
    """Создание собрания: вид, дата и кто проводит."""

    kind = forms.ChoiceField(label='Вид собрания', choices=MeetingKind.choices)
    host = forms.ModelChoiceField(
        label='Какой тимлид проводит', queryset=Intern.objects.none(),
        required=False, empty_label='Любой / не указан',
    )
    topic = forms.CharField(
        label='Тема (необязательно)', required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Например: недельный статус'}),
    )

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        if group is not None:
            # В списке — только тимлиды этой группы
            self.fields['host'].queryset = Intern.objects.filter(
                team_memberships__group=group,
                team_memberships__role='team_lead',
                team_memberships__status='active',
            ).distinct().order_by('full_name')


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
    """Табель группы: посещаемость собраний за месяц."""
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
    })


@login_required
def meeting_create(request, pk):
    """Создать одно собрание группы на выбранную дату."""
    group = get_object_or_404(Group.objects.select_related('flow'), pk=pk)
    year, month = _period(request)
    form = MeetingCreateForm(request.POST or None, group=group)

    date_error = ''
    if request.method == 'POST' and form.is_valid():
        dates = []
        for raw in request.POST.getlist('date'):
            raw = raw.strip()
            if not raw:
                continue
            try:
                dates.append(datetime.date.fromisoformat(raw))
            except ValueError:
                continue
        if not dates:
            date_error = 'Укажите хотя бы одну дату собрания.'
        else:
            created = [
                services.create_meeting(
                    group,
                    kind=form.cleaned_data['kind'],
                    date=date,
                    host=form.cleaned_data.get('host'),
                    topic=form.cleaned_data.get('topic', ''),
                )
                for date in sorted(set(dates))
            ]
            new_count = len([item for item in created if item])
            if new_count:
                messages.success(request, f'Добавлено собраний: {new_count}.')
            else:
                messages.info(request, 'Такие собрания уже есть в табеле.')
            first = sorted(set(dates))[0]
            return redirect(
                f'/attendance/groups/{group.pk}/'
                f'?year={first.year}&month={first.month}',
            )

    return render(request, 'attendance/meeting_form.html', {
        'group': group,
        'form': form,
        'year': year,
        'month': month,
        'current': datetime.date(year, month, 1),
        'today': timezone.localdate(),
        'date_error': date_error,
    })


@login_required
def meeting_delete(request, pk):
    """Удалить собрание вместе с его отметками."""
    meeting = get_object_or_404(
        GroupMeeting.objects.select_related('group'), pk=pk,
    )
    group, date = meeting.group, meeting.date
    if request.method == 'POST':
        meeting.delete()
        messages.success(request, 'Собрание удалено.')
    return redirect(
        f'/attendance/groups/{group.pk}/?year={date.year}&month={date.month}',
    )


@login_required
def toggle(request, pk):
    """AJAX: клик по клетке табеля переключает отметку."""
    meeting = get_object_or_404(
        GroupMeeting.objects.select_related('group'), pk=pk,
    )
    if request.method != 'POST':
        raise Http404
    intern = get_object_or_404(Intern, pk=request.POST.get('intern'))
    mark = services.toggle_mark(meeting, intern, user=request.user)
    return render(request, 'attendance/partials/cell.html', {
        'intern': intern,
        'cell': {'meeting': meeting, 'status': mark.status if mark else ''},
    })


@login_required
def meeting_mark_all(request, pk):
    """Отметить всю команду присутствующей на собрании."""
    meeting = get_object_or_404(
        GroupMeeting.objects.select_related('group'), pk=pk,
    )
    if request.method == 'POST':
        created = services.mark_all_present(meeting, user=request.user)
        messages.success(request, f'Отмечено присутствующих: {created}.')
    return redirect(
        f'/attendance/groups/{meeting.group.pk}/'
        f'?year={meeting.date.year}&month={meeting.date.month}',
    )


@login_required
def dashboard(request):
    """Табель: собрания сегодня и посещаемость по всем группам."""
    year, month = _period(request)
    current = datetime.date(year, month, 1)
    prev_month = (current - datetime.timedelta(days=1)).replace(day=1)
    next_month = (current + datetime.timedelta(days=32)).replace(day=1)

    rows = overview.groups_summary(year, month)
    total_meetings = sum(row['meetings'] for row in rows)
    total_held = sum(row['held'] for row in rows)
    rates = [row['rate'] for row in rows if row['rate'] is not None]

    return render(request, 'attendance/dashboard.html', {
        'rows': rows,
        'today_meetings': overview.today_meetings(),
        'week_meetings': overview.week_meetings(),
        'total_meetings': total_meetings,
        'total_held': total_held,
        'average_rate': round(sum(rates) / len(rates)) if rates else None,
        'year': year,
        'month': month,
        'current': current,
        'prev_month': prev_month,
        'next_month': next_month,
        'today': timezone.localdate(),
    })
