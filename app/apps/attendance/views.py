import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.attendance import services
from apps.attendance.models import (
    Attendance,
    GroupMeeting,
    MeetingKind,
    MeetingPlan,
    WEEKDAYS,
)
from apps.flows.models import Group
from apps.interns.models import Intern


class MeetingPlanForm(forms.ModelForm):
    """План: какие собрания и сколько раз в неделю проводит группа."""

    weekday_choices = forms.MultipleChoiceField(
        label='Дни недели', choices=WEEKDAYS, required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = MeetingPlan
        fields = ['kind', 'times_per_week', 'host']
        labels = {'kind': 'Вид собрания', 'host': 'Кто проводит'}

    def __init__(self, *args, group=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        if group is not None:
            self.fields['host'].queryset = Intern.objects.filter(
                team_memberships__group=group,
            ).distinct().order_by('full_name')
        self.fields['host'].required = False
        self.fields['host'].empty_label = 'Не указан'
        if self.instance.pk:
            self.fields['weekday_choices'].initial = [
                str(day) for day in self.instance.weekday_list
            ]

    def save(self, commit=True):
        plan = super().save(commit=False)
        plan.weekdays = ','.join(self.cleaned_data.get('weekday_choices', []))
        if self.group is not None:
            plan.group = self.group
        if commit:
            plan.save()
        return plan


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
    """Табель группы: посещаемость запланированных собраний за месяц."""
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
        'plans': group.meeting_plans.select_related('host'),
        'year': year,
        'month': month,
        'current': current,
        'prev_month': prev_month,
        'next_month': next_month,
        'today': timezone.localdate(),
    })


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
def plan_list(request, pk):
    """План собраний группы: сколько и каких собраний в неделю."""
    group = get_object_or_404(Group.objects.select_related('flow'), pk=pk)
    form = MeetingPlanForm(request.POST or None, group=group)
    if request.method == 'POST' and form.is_valid():
        plan = form.save()
        messages.success(request, f'План «{plan}» добавлен.')
        return redirect('attendance:plan_list', pk=group.pk)
    return render(request, 'attendance/plan_list.html', {
        'group': group,
        'plans': group.meeting_plans.select_related('host'),
        'form': form,
        'kinds': MeetingKind.choices,
    })


@login_required
def plan_delete(request, pk):
    plan = get_object_or_404(MeetingPlan.objects.select_related('group'), pk=pk)
    group = plan.group
    if request.method == 'POST':
        plan.delete()
        messages.success(request, 'План удалён.')
    return redirect('attendance:plan_list', pk=group.pk)


@login_required
def generate(request, pk):
    """Создать собрания месяца по плану группы."""
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        try:
            year = int(request.POST.get('year'))
            month = int(request.POST.get('month'))
        except (TypeError, ValueError):
            today = timezone.localdate()
            year, month = today.year, today.month
        if not group.meeting_plans.filter(is_active=True).exists():
            messages.error(
                request,
                'Сначала составьте план собраний — сколько раз в неделю и какие.',
            )
            return redirect('attendance:plan_list', pk=group.pk)
        created = services.generate_meetings(group, year, month, user=request.user)
        messages.success(request, f'Создано собраний: {created}.')
        return redirect(
            f'/attendance/groups/{group.pk}/?year={year}&month={month}',
        )
    return redirect('attendance:group_sheet', pk=group.pk)
