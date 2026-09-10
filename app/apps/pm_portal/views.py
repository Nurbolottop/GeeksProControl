import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.attendance import services as attendance_services
from apps.attendance.models import GroupMeeting, MeetingKind, WorkScore
from apps.documents import services as document_services
from apps.pm_portal import services
from apps.pm_portal.forms import PMClientForm, PMDocumentForm
from apps.projects.models import ProjectReport
from apps.projects.services import calculate_deadline_status
from apps.teams.forms import TeamMemberEditForm, TeamMemberForm
from apps.teams.models import TeamMember
from apps.teams.selectors import group_by_role
from apps.teams.views import _role_from, _title_for, _with_new_person, people_options
from apps.training.models import Specialization


@login_required
def dashboard(request):
    """Список проектов, где текущий пользователь — активный ПМ."""
    return render(request, 'pm_portal/dashboard.html', {
        'projects': services.pm_projects(request.user),
    })


@login_required
def project_detail(request, pk):
    """Обзор проекта — только чтение: статус/этап/дедлайн менять здесь нельзя."""
    project = services.pm_project_or_404(request.user, pk)
    project.deadline_status = calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {'project': project, 'tab': tab}
    if tab == 'report':
        context['reports'] = project.reports.select_related('author')
    elif tab == 'team':
        members = project.team_members.select_related('intern__specialization', 'user')
        context['team_sections'] = group_by_role(members)
        context['team_members'] = list(members)
    elif tab == 'attendance':
        group = getattr(project, 'group', None)
        context['group'] = group
        if group:
            context['meetings'] = group.meetings.select_related('host').order_by('-date')
    elif tab == 'documents':
        document_services.ensure_default_types()
        context['documents'] = project.documents.active().select_related('doc_type')
    elif tab == 'client':
        context['client'] = project.client
    return render(request, 'pm_portal/project_detail.html', context)


def _group_or_404(project):
    group = getattr(project, 'group', None)
    if group is None:
        raise Http404('У проекта ещё нет группы в потоке.')
    return group


@login_required
def meeting_create(request, pk):
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    if request.method == 'POST':
        raw = request.POST.get('date', '').strip()
        try:
            date = datetime.date.fromisoformat(raw)
        except ValueError:
            messages.error(request, 'Укажите корректную дату.')
        else:
            meeting = attendance_services.create_meeting(
                group, kind=MeetingKind.INTERNAL, date=date,
            )
            if meeting:
                messages.success(request, f'Собрание {date:%d.%m.%Y} добавлено.')
            else:
                messages.info(request, 'Такое собрание уже есть.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=attendance")


@login_required
def meeting_detail(request, pk, meeting_pk):
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    marks = {mark.intern_id: mark for mark in meeting.attendance.all()}
    scores = {score.intern_id: score for score in meeting.scores.all()}
    previous = attendance_services.previous_scores(meeting)
    members = list(
        group.members.select_related('intern__specialization')
        .filter(intern__isnull=False).order_by('role', 'intern__full_name'),
    )
    for member in members:
        member.mark = marks.get(member.intern_id)
        score = scores.get(member.intern_id)
        value = score.score if score else None
        member.score = attendance_services.score_row(
            meeting, member.intern, score=value,
            comment=score.comment if score else '',
            previous=previous.get(member.intern_id),
        )
    sections = [
        section for section in group_by_role(members) if section['members']
    ]
    attended = sum(
        1 for m in members if m.mark and m.mark.status in ('present', 'late')
    )
    marked = sum(1 for m in members if m.mark)
    given = [m.score['score'] for m in members if m.score['score'] is not None]
    return render(request, 'pm_portal/meeting_detail.html', {
        'project': project, 'group': group, 'meeting': meeting,
        'sections': sections,
        'marked': marked, 'attended': attended, 'total_people': len(members),
        'rate': round(attended / marked * 100) if marked else None,
        'scored': len(given),
        'average_score': round(sum(given) / len(given), 1) if given else None,
        'period_start': meeting.period_start, 'period_days': meeting.period_days,
        'tab': 'scores' if request.GET.get('tab') == 'scores' else 'marks',
    })


@login_required
def meeting_score(request, pk, meeting_pk):
    """Клик по шкале «Активность» — балл (0–10) или комментарий за период."""
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method != 'POST':
        raise Http404
    member = get_object_or_404(
        group.members.select_related('intern__specialization').filter(intern__isnull=False),
        intern_id=request.POST.get('intern'),
    )
    intern = member.intern
    entry = WorkScore.objects.filter(meeting=meeting, intern=intern).first()

    if 'comment' in request.POST:
        comment = request.POST.get('comment', '').strip()[:255]
        if entry:
            entry.comment = comment
            entry.save(update_fields=['comment', 'marked_by', 'updated_at'])
        elif comment:
            entry = WorkScore.objects.create(
                meeting=meeting, intern=intern,
                score=0, comment=comment, marked_by=request.user,
            )
    else:
        raw = request.POST.get('score', '')
        if raw.isdigit() and 0 <= int(raw) <= WorkScore.MAX:
            value = int(raw)
            if entry:
                entry.score = value
                entry.marked_by = request.user
                entry.save(update_fields=['score', 'marked_by', 'updated_at'])
            else:
                entry = WorkScore.objects.create(
                    meeting=meeting, intern=intern, score=value,
                    marked_by=request.user,
                )
        elif entry:
            entry.delete()
            entry = None

    member.score = attendance_services.score_row(
        meeting, intern,
        score=entry.score if entry else None,
        comment=entry.comment if entry else '',
        previous=attendance_services.previous_scores(meeting).get(intern.pk),
    )
    return render(request, 'pm_portal/partials/score_row.html', {
        'project': project, 'meeting': meeting, 'member': member,
    })


@login_required
def meeting_mark_toggle(request, pk, meeting_pk):
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method == 'POST':
        intern = get_object_or_404(
            group.members.filter(intern__isnull=False), intern_id=request.POST.get('intern'),
        ).intern
        attendance_services.toggle_mark(meeting, intern, user=request.user)
    return redirect('pm_portal:meeting_detail', pk=project.pk, meeting_pk=meeting.pk)


@login_required
def meeting_mark_all(request, pk, meeting_pk):
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method == 'POST':
        created = attendance_services.mark_all_present(meeting, user=request.user)
        messages.success(request, f'Отмечено присутствующих: {created}.')
    return redirect('pm_portal:meeting_detail', pk=project.pk, meeting_pk=meeting.pk)


@login_required
def report_create(request, pk):
    project = services.pm_project_or_404(request.user, pk)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if not text:
            messages.error(request, 'Отчёт пустой — напишите текст.')
        else:
            report = ProjectReport.objects.create(
                project=project, text=text, author=request.user,
            )
            messages.success(request, f'Отчёт от {report.date:%d.%m.%Y} сохранён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")


@login_required
def report_update(request, pk, report_pk):
    project = services.pm_project_or_404(request.user, pk)
    report = get_object_or_404(ProjectReport, pk=report_pk, project=project)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            report.text = text
            report.save(update_fields=['text', 'updated_at'])
            messages.success(request, 'Отчёт обновлён.')
        else:
            messages.error(request, 'Отчёт пустой — текст не сохранён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")


@login_required
def report_delete(request, pk, report_pk):
    project = services.pm_project_or_404(request.user, pk)
    report = get_object_or_404(ProjectReport, pk=report_pk, project=project)
    if request.method == 'POST':
        date = report.date
        report.delete()
        messages.success(request, f'Отчёт от {date:%d.%m.%Y} удалён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")


def _team_url(project):
    return f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=team"


@login_required
def member_add(request, pk):
    project = services.pm_project_or_404(request.user, pk)
    role = _role_from(request)
    form = TeamMemberForm(request.POST or None, role=role)
    created_person = None
    if request.method == 'POST':
        data, created_person = _with_new_person(request, role=role)
        form = TeamMemberForm(data, role=role)
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.project = project
        member.group = getattr(project, 'group', None)
        member.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        if created_person:
            messages.success(request, f'{created_person} заведён(а) в базе.')
        messages.success(request, f'{member.person_name} добавлен(а) в команду.')
        return redirect(_team_url(project))
    return render(
        request, 'pm_portal/member_form.html',
        {'form': form, 'project': project,
         'people': people_options(form),
         'specializations': Specialization.objects.order_by('name'),
         'role': role,
         'title': _title_for(role)},
    )


@login_required
def member_edit(request, pk, member_pk):
    project = services.pm_project_or_404(request.user, pk)
    member = get_object_or_404(TeamMember, pk=member_pk, project=project)
    form = TeamMemberEditForm(request.POST or None, instance=member)
    if request.method == 'POST' and form.is_valid():
        form.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        messages.success(request, 'Участник обновлён.')
        return redirect(_team_url(project))
    return render(
        request, 'pm_portal/member_form.html',
        {
            'form': form, 'project': project,
            'people': people_options(form),
            'specializations': Specialization.objects.order_by('name'),
            'selected_id': member.intern_id,
            'selected_name': member.person_name,
            'title': f'Редактирование: {member.person_name}',
        },
    )


@login_required
def member_delete(request, pk, member_pk):
    project = services.pm_project_or_404(request.user, pk)
    member = get_object_or_404(TeamMember, pk=member_pk, project=project)
    if request.method == 'POST':
        name = member.person_name
        member.delete()
        messages.success(request, f'{name} убран(а) из команды.')
    return redirect(_team_url(project))


@login_required
def intern_detail(request, pk, intern_pk):
    """Детальная карточка стажёра — только по своему проекту, только чтение.

    Ручных оценок в ПМ-портале нет — только «Активность» (WorkScore),
    которая и так уже ставится на собраниях (вкладка «Табель»).
    """
    project = services.pm_project_or_404(request.user, pk)
    member = get_object_or_404(
        TeamMember.objects.select_related('intern__specialization'),
        project=project, intern_id=intern_pk, status=TeamMember.Status.ACTIVE,
    )
    intern = member.intern
    group = getattr(project, 'group', None)
    scores = (
        WorkScore.objects.filter(intern=intern, meeting__group=group)
        .select_related('meeting').order_by('-meeting__date')
        if group else WorkScore.objects.none()
    )
    values = [item.score for item in scores]
    return render(request, 'pm_portal/intern_detail.html', {
        'project': project, 'member': member, 'intern': intern,
        'scores': scores,
        'average_score': round(sum(values) / len(values), 1) if values else None,
    })


@login_required
def document_upload(request, pk):
    project = services.pm_project_or_404(request.user, pk)
    document_services.ensure_default_types()
    form = PMDocumentForm(
        request.POST or None, request.FILES or None, project=project,
    )
    if request.method == 'POST' and form.is_valid():
        document = form.save()
        messages.success(request, f'Документ «{document.doc_type}» добавлен.')
        return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=documents")
    return render(request, 'pm_portal/document_form.html', {
        'form': form, 'project': project,
    })


@login_required
def client_edit(request, pk):
    """Данные заказчика этого проекта — заполняет ПМ."""
    project = services.pm_project_or_404(request.user, pk)
    form = PMClientForm(request.POST or None, instance=project.client)
    if request.method == 'POST' and form.is_valid():
        client = form.save()
        if project.client_id != client.pk:
            project.client = client
            project.save(update_fields=['client', 'updated_at'])
        messages.success(request, 'Данные клиента сохранены.')
        return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=client")
    return render(request, 'pm_portal/client_form.html', {
        'form': form, 'project': project,
    })
