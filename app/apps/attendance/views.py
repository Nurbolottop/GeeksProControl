import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.attendance import services
from apps.attendance.models import GroupMeeting, MeetingKind, WEEKDAYS
from apps.flows.models import Group
from apps.interns.models import Intern


class MeetingCreateForm(forms.Form):
    """Создание собраний: вид, дни недели и кто проводит."""

    kind = forms.ChoiceField(label='Вид собрания', choices=MeetingKind.choices)
    weekdays = forms.MultipleChoiceField(
        label='Дни недели', choices=WEEKDAYS,
        widget=forms.CheckboxSelectMultiple,
        error_messages={'required': 'Выберите хотя бы один день недели.'},
    )
    host = forms.ModelChoiceField(
        label='Кто проводит', queryset=Intern.objects.none(),
        required=False, empty_label='Не указан',
    )
    topic = forms.CharField(
        label='Тема (необязательно)', required=False, max_length=255,
        widget=forms.TextInput(attrs={'placeholder': 'Например: недельный статус'}),
    )

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        if group is not None:
            self.fields['host'].queryset = Intern.objects.filter(
                team_memberships__group=group,
            ).distinct().order_by('full_name')

    @property
    def weekday_numbers(self) -> list[int]:
        return [int(value) for value in self.cleaned_data['weekdays']]


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
    """Создать собрания группы в выбранные дни недели месяца."""
    group = get_object_or_404(Group.objects.select_related('flow'), pk=pk)
    year, month = _period(request)
    form = MeetingCreateForm(request.POST or None, group=group)

    if request.method == 'POST' and form.is_valid():
        created = services.create_meetings(
            group,
            kind=form.cleaned_data['kind'],
            weekdays=form.weekday_numbers,
            year=year, month=month,
            host=form.cleaned_data.get('host'),
            topic=form.cleaned_data.get('topic', ''),
        )
        if created:
            messages.success(request, f'Добавлено собраний: {created}.')
        else:
            messages.info(
                request, 'Такие собрания в этом месяце уже есть.',
            )
        return redirect(
            f'/attendance/groups/{group.pk}/?year={year}&month={month}',
        )

    return render(request, 'attendance/meeting_form.html', {
        'group': group,
        'form': form,
        'year': year,
        'month': month,
        'current': datetime.date(year, month, 1),
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
