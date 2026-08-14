from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.meetings import services
from apps.meetings.forms import MeetingDecisionForm, MeetingForm
from apps.meetings.models import Meeting, MeetingType


@login_required
def meeting_list(request):
    qs = Meeting.objects.select_related('project')
    params = request.GET
    if params.get('type'):
        qs = qs.filter(meeting_type=params['type'])
    if params.get('project'):
        qs = qs.filter(project_id=params['project'])
    paginator = Paginator(qs, 25)
    page = paginator.get_page(params.get('page'))
    from apps.projects.models import Project
    context = {
        'page': page,
        'params': params,
        'types': MeetingType.choices,
        'projects': Project.objects.active().order_by('name'),
    }
    return render(request, 'meetings/list.html', context)


@login_required
def meeting_detail(request, pk):
    meeting = get_object_or_404(
        Meeting.objects.select_related('project').prefetch_related('participants'),
        pk=pk,
    )
    decision_form = MeetingDecisionForm()
    if request.method == 'POST':
        decision_form = MeetingDecisionForm(request.POST)
        if decision_form.is_valid():
            decision = decision_form.save(commit=False)
            decision.meeting = meeting
            decision.save()
            messages.success(request, 'Решение добавлено.')
            return redirect(meeting.get_absolute_url())
    context = {
        'meeting': meeting,
        'decisions': meeting.decisions.select_related('responsible', 'task'),
        'decision_form': decision_form,
    }
    return render(request, 'meetings/detail.html', context)


@login_required
def meeting_create(request):
    initial = {}
    if request.GET.get('agenda') == 'auto':
        agenda_points = services.build_auto_agenda()
        initial['agenda'] = '\n'.join(f'— {point}' for point in agenda_points)
    form = MeetingForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        meeting = form.save()
        form.save_m2m()
        messages.success(request, f'Собрание «{meeting.topic}» создано.')
        return redirect(meeting.get_absolute_url())
    return render(
        request, 'meetings/form.html',
        {'form': form, 'title': 'Новое собрание'},
    )


@login_required
def meeting_update(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    form = MeetingForm(request.POST or None, instance=meeting)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Собрание обновлено.')
        return redirect(meeting.get_absolute_url())
    return render(
        request, 'meetings/form.html',
        {'form': form, 'title': f'Редактирование: {meeting.topic}', 'meeting': meeting},
    )


@login_required
def decision_create_task(request, pk):
    """Кнопка «Создать задачу» у решения (ТЗ §19.2)."""
    from apps.meetings.models import MeetingDecision
    decision = get_object_or_404(
        MeetingDecision.objects.select_related('meeting'), pk=pk,
    )
    if request.method == 'POST':
        task = services.create_task_from_decision(decision, user=request.user)
        messages.success(request, f'Задача «{task.title}» создана.')
    return redirect(decision.meeting.get_absolute_url())
