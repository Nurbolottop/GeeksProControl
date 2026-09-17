from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.attendance import services as attendance_services
from apps.attendance.models import GroupMeeting, WorkScore
from apps.documents import services as document_services
from apps.documents.models import Document, DocumentStatus
from apps.pm_portal import services, stages as stage_reminders
from apps.pm_portal.forms import PMClientForm, PMDocumentForm
from apps.projects.models import ProjectReport, ProjectStage
from apps.projects.services import calculate_deadline_status
from apps.teams.forms import TeamMemberEditForm, TeamMemberForm
from apps.teams.models import TeamMember
from apps.teams.selectors import group_by_role
from apps.teams.views import _role_from, _title_for, _with_new_person, people_options
from apps.training.models import Specialization


@login_required
def dashboard(request):
    """Список проектов, где текущий пользователь — активный ПМ."""
    from apps.projects.models import ProjectStatus

    category = request.GET.get('status', 'all')
    projects = services.pm_projects(request.user)
    if category == 'in_progress':
        projects = projects.filter(status__in=[ProjectStatus.ACTIVE, ProjectStatus.PAUSED])
    elif category == 'completed':
        projects = projects.filter(status=ProjectStatus.COMPLETED)
    elif category == 'cancelled':
        projects = projects.filter(status__in=[ProjectStatus.CANCELLED, ProjectStatus.REFUSED])
    else:
        category = 'all'
    projects = list(projects)
    for project in projects:
        project.stage_check_needed = stage_reminders.needs_stage_check(project)
    return render(request, 'pm_portal/dashboard.html', {
        'projects': projects, 'category': category,
    })


@login_required
def project_detail(request, pk):
    """Проект глазами ПМ. Этапы ПМ двигает сам; статус проекта, дедлайн
    и завершение — только у руководителя в основном приложении."""
    project = services.pm_project_or_404(request.user, pk)
    project.deadline_status = calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {
        'project': project, 'tab': tab,
        'stage_check_needed': stage_reminders.needs_stage_check(project),
    }
    if tab == 'stages':
        context['stages'] = stage_reminders.editable_stages(project)
        context['stage_statuses'] = ProjectStage.Status.choices
    elif tab == 'report':
        context['reports'] = project.reports.select_related('author')
    elif tab == 'team':
        members = project.team_members.select_related('intern__specialization', 'user')
        is_mobile = bool(project.project_type and project.project_type.is_mobile)
        context['team_sections'] = group_by_role(members, is_mobile)
        context['team_members'] = list(members)
    elif tab == 'attendance':
        group = getattr(project, 'group', None)
        context['group'] = group
        if group:
            context['meetings'] = group.meetings.select_related('host').order_by('-date')
    elif tab == 'documents':
        from apps.documents.models import DocumentType

        document_services.ensure_default_types()
        documents = list(project.documents.active().select_related('doc_type'))
        by_type = {}
        for document in documents:
            by_type.setdefault(document.doc_type_id, document)
        context['checklist'] = [
            {'type': doc_type, 'document': by_type.get(doc_type.pk)}
            for doc_type in DocumentType.objects.order_by(
                '-required_for_delivery', 'name',
            )
        ]
        context['documents'] = documents
        context['doc_progress'] = document_services.document_progress(project)
        context['brief_link'] = document_services.active_brief_link(project)
        context['project_brief'] = getattr(project, 'brief', None)
    elif tab == 'client':
        context['client'] = project.client
    else:
        # «Обзор»: путь проекта, живые цифры и хронология — как «Графика»
        # в основном приложении
        from apps.projects.graphics import graphics_context

        context.update(graphics_context(project))
    return render(request, 'pm_portal/project_detail.html', context)


def _stages_url(project):
    return f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=stages"


@login_required
def stage_set(request, pk, stage_pk):
    """ПМ меняет статус одного этапа: не начат / в процессе / завершён."""
    project = services.pm_project_or_404(request.user, pk)
    if request.method != 'POST':
        return redirect(_stages_url(project))
    stage = get_object_or_404(
        ProjectStage.objects.exclude(key='completed'), pk=stage_pk, project=project,
    )
    status = request.POST.get('status', '')
    if status not in dict(ProjectStage.Status.choices):
        messages.error(request, 'Выберите статус этапа из списка.')
        return redirect(_stages_url(project))
    if stage_reminders.set_stage_status(project, stage, status, user=request.user):
        messages.success(
            request,
            f'Этап «{stage.get_key_display()}»: {stage.get_status_display().lower()}.',
        )
    else:
        messages.info(request, 'Этап уже в этом статусе — отметили, что этапы сверены.')
    return redirect(_stages_url(project))


@login_required
def stages_confirm(request, pk):
    """«Этап актуален» — ничего не менялось, но ПМ сверил этапы сегодня."""
    project = services.pm_project_or_404(request.user, pk)
    if request.method == 'POST':
        stage_reminders.mark_checked(project)
        messages.success(request, 'Спасибо! Этапы сверены — напоминание погасло до завтра.')
    # возвращаем туда, где нажали кнопку, но только внутри сайта
    next_url = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        next_url = _stages_url(project)
    return redirect(next_url)


def _group_or_404(project):
    group = getattr(project, 'group', None)
    if group is None:
        raise Http404('У проекта ещё нет группы в потоке.')
    return group


@login_required
def meeting_detail(request, pk, meeting_pk):
    """Табель собрания у ПМ — только просмотр: отмечает и оценивает
    теперь тимлид, ПМ видит результат."""
    project = services.pm_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    marks = {mark.intern_id: mark for mark in meeting.attendance.all()}
    scores = {score.intern_id: score for score in meeting.scores.all()}
    previous = attendance_services.previous_scores(meeting)
    members = list(
        attendance_services.attendance_eligible_members(group)
        .select_related('intern__specialization')
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
    initial = {}
    if request.GET.get('type'):
        initial['doc_type'] = request.GET['type']
    form = PMDocumentForm(
        request.POST or None, request.FILES or None, project=project, initial=initial,
    )
    if request.method == 'POST' and form.is_valid():
        document = form.save()
        messages.success(request, f'Документ «{document.doc_type}» добавлен.')
        return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=documents")
    return render(request, 'pm_portal/document_form.html', {
        'form': form, 'project': project,
    })


@login_required
def document_update(request, pk, document_pk):
    project = services.pm_project_or_404(request.user, pk)
    document = get_object_or_404(Document, pk=document_pk, project=project)
    form = PMDocumentForm(
        request.POST or None, request.FILES or None, project=project, instance=document,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Документ обновлён.')
        return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=documents")
    return render(request, 'pm_portal/document_form.html', {
        'form': form, 'project': project,
    })


@login_required
def document_approve(request, pk, document_pk):
    """Утвердить документ: бриф принят, ТЗ/акт согласован с заказчиком."""
    project = services.pm_project_or_404(request.user, pk)
    document = get_object_or_404(Document, pk=document_pk, project=project)
    if request.method == 'POST':
        document.status = DocumentStatus.SIGNED
        document.is_signed = True
        if not document.signed_date:
            document.signed_date = timezone.localdate()
        document.save(update_fields=[
            'status', 'is_signed', 'signed_date', 'updated_at',
        ])
        messages.success(request, f'«{document.doc_type}» утверждён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=documents")


@login_required
def brief_link_create(request, pk):
    """Новая ссылка на бриф проекта — ПМ копирует и отправляет заказчику сам."""
    project = services.pm_project_or_404(request.user, pk)
    if request.method == 'POST':
        document_services.issue_brief_link(project, user=request.user)
        messages.success(request, 'Ссылка на бриф создана.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=documents")


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
