import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.attendance import services as attendance_services
from apps.attendance.models import GroupMeeting, MeetingKind, WorkScore
from apps.lead_portal import services
from apps.projects.services import calculate_deadline_status
from apps.teams.forms import TeamMemberEditForm, TeamMemberForm
from apps.teams.models import TeamMember
from apps.teams.selectors import ROLE_LABELS, ROLE_TONE, group_by_role
from apps.teams.views import _title_for, _with_new_person, people_options
from apps.training.models import Specialization


@login_required
def dashboard(request):
    """Список проектов, где текущий пользователь — активный тимлид."""
    from apps.notifications.services import personal
    from apps.projects.models import ProjectStatus
    from apps.reserve.services import reserve_card_of

    category = request.GET.get('status', 'all')
    projects = services.lead_projects(request.user)
    if category == 'in_progress':
        projects = projects.filter(status__in=[ProjectStatus.ACTIVE, ProjectStatus.PAUSED])
    elif category == 'completed':
        projects = projects.filter(status=ProjectStatus.COMPLETED)
    elif category == 'cancelled':
        projects = projects.filter(status__in=[ProjectStatus.CANCELLED, ProjectStatus.REFUSED])
    else:
        category = 'all'

    notifications = list(personal(getattr(request.user, 'intern_profile', None)))
    response = render(request, 'lead_portal/dashboard.html', {
        'projects': list(projects),
        'resume': reserve_card_of(request.user),
        'notifications': notifications,
        'category': category,
    })
    # показали на главной — значит прочитано; висит, пока не нажмут «Понятно»
    unread = [note.pk for note in notifications if not note.is_read]
    if unread:
        from apps.notifications.models import Notification

        Notification.objects.filter(pk__in=unread).update(is_read=True)
    return response


@login_required
def notification_close(request, pk):
    """«Понятно» — закрыть своё уведомление. Чужие закрыть нельзя."""
    from apps.notifications.services import personal

    if request.method == 'POST':
        personal(getattr(request.user, 'intern_profile', None)).filter(pk=pk).update(
            is_closed=True, is_read=True,
        )
    return redirect('lead_portal:dashboard')


@login_required
def resume(request):
    """Моё резюме в резерве кадров: правлю сам, под своим логином, без ссылок.

    Тимлиды попадают в резерв автоматически — здесь человек ведёт своё
    резюме. Оценки, статусы и комментарии сотрудников сюда не
    попадают: форма та же, что у публичной анкеты.
    """
    import json

    from apps.reserve import services as reserve_services
    from apps.reserve.forms import ReserveApplyForm

    candidate = reserve_services.reserve_card_of(request.user)
    person = getattr(request.user, 'intern_profile', None)
    if candidate is None and person is not None:
        from apps.teams.models import TeamMember, TeamRole

        # тимлид всегда в резерве — если карточки почему-то нет, заводим сразу
        if TeamMember.objects.filter(intern=person, role=TeamRole.TEAM_LEAD).exists():
            reserve_services.ensure_lead_in_reserve(person)
            candidate = reserve_services.reserve_card_of(request.user)
    if candidate is None:
        return render(request, 'lead_portal/resume.html', {'candidate': None})
    form = ReserveApplyForm(
        request.POST or None, request.FILES or None, instance=candidate,
    )
    if request.method == 'POST' and form.is_valid():
        reserve_services.save_own_resume(candidate, form, request.user)
        messages.success(request, 'Резюме сохранено — в резерве кадров уже новая версия.')
        return redirect('lead_portal:resume')
    return render(request, 'lead_portal/resume.html', {
        'candidate': candidate,
        'form': form,
        'direction_groups': json.dumps(reserve_services.direction_groups_map()),
        'mark_optional': True,
    })


@login_required
def project_detail(request, pk):
    """Проект глазами тимлида: своя команда и табель — статус, дедлайн,
    документы и клиент остаются в основном приложении/у ПМ."""
    project = services.lead_project_or_404(request.user, pk)
    project.deadline_status = calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {'project': project, 'tab': tab}
    if tab == 'team':
        from apps.interns.services import active_profile_form_link
        from apps.interns.views import PROFILE_LINK_TTL_CHOICES

        context['profile_link'] = active_profile_form_link(project)
        context['profile_link_ttls'] = PROFILE_LINK_TTL_CHOICES
        own_role = services.lead_own_role(request.user)
        members = project.team_members.select_related('intern__specialization', 'user')
        if own_role:
            members = members.filter(role=own_role)
        is_mobile = bool(project.project_type and project.project_type.is_mobile)
        sections = group_by_role(members, is_mobile)
        if own_role:
            # group_by_role всегда показывает пустые секции ПМ/тимлида/etc
            # (ALWAYS_SHOWN) — тимлиду нужна только его собственная, и
            # даже если в ней пока никого нет (иначе некуда добавлять).
            sections = [s for s in sections if s['role'] == own_role] or [{
                'role': own_role,
                'label': ROLE_LABELS.get(own_role, own_role),
                'tone': ROLE_TONE.get(own_role, 'gray'),
                'members': [], 'count': 0, 'active': 0,
            }]
        context['team_sections'] = sections
        context['team_members'] = list(members)
        context['own_role'] = own_role
    elif tab == 'attendance':
        group = getattr(project, 'group', None)
        context['group'] = group
        if group:
            context['meetings'] = group.meetings.select_related('host').order_by('-date')
    else:
        from apps.lead_portal.overview import lead_overview

        context.update(lead_overview(project, services.lead_own_role(request.user)))
        context['today'] = timezone.localdate()
    return render(request, 'lead_portal/project_detail.html', context)


def _team_url(project):
    return f"{reverse('lead_portal:project_detail', args=[project.pk])}?tab=team"


@login_required
def member_add(request, pk):
    """Тимлид добавляет только в своё направление — роль из ссылки
    игнорируется, берём всегда его собственную специализацию."""
    project = services.lead_project_or_404(request.user, pk)
    role = services.lead_own_role(request.user)
    if role is None:
        messages.error(
            request,
            'У вас не заполнено направление (специализация) — обратитесь '
            'к руководителю, чтобы добавлять участников команды.',
        )
        return redirect(_team_url(project))
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
        request, 'lead_portal/member_form.html',
        {'form': form, 'project': project,
         'people': people_options(form),
         'specializations': Specialization.objects.order_by('name'),
         'role': role,
         'title': _title_for(role)},
    )


def _own_direction_member_or_404(request, project, member_pk):
    """Тимлид правит/убирает только участников своего направления."""
    own_role = services.lead_own_role(request.user)
    return get_object_or_404(
        TeamMember, pk=member_pk, project=project, role=own_role,
    )


@login_required
def member_edit(request, pk, member_pk):
    project = services.lead_project_or_404(request.user, pk)
    member = _own_direction_member_or_404(request, project, member_pk)
    form = TeamMemberEditForm(request.POST or None, instance=member)
    if request.method == 'POST' and form.is_valid():
        form.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        messages.success(request, 'Участник обновлён.')
        return redirect(_team_url(project))
    return render(
        request, 'lead_portal/member_form.html',
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
    project = services.lead_project_or_404(request.user, pk)
    member = _own_direction_member_or_404(request, project, member_pk)
    if request.method == 'POST':
        name = member.person_name
        member.delete()
        messages.success(request, f'{name} убран(а) из команды.')
    return redirect(_team_url(project))


def _group_or_404(project):
    group = getattr(project, 'group', None)
    if group is None:
        raise Http404('У проекта ещё нет группы в потоке.')
    return group


@login_required
def meeting_create(request, pk):
    project = services.lead_project_or_404(request.user, pk)
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
    return redirect(f"{reverse('lead_portal:project_detail', args=[project.pk])}?tab=attendance")


def _own_direction_eligible_members(request, group):
    """Кого тимлид может отмечать/оценивать на собрании — только своё
    направление (ПМ и другие тимлиды и так исключены отдельно)."""
    members = attendance_services.attendance_eligible_members(group)
    own_role = services.lead_own_role(request.user)
    if own_role:
        members = members.filter(role=own_role)
    return members


@login_required
def meeting_detail(request, pk, meeting_pk):
    project = services.lead_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    marks = {mark.intern_id: mark for mark in meeting.attendance.all()}
    scores = {score.intern_id: score for score in meeting.scores.all()}
    previous = attendance_services.previous_scores(meeting)
    members = list(
        _own_direction_eligible_members(request, group)
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
    return render(request, 'lead_portal/meeting_detail.html', {
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
def meeting_mark_toggle(request, pk, meeting_pk):
    """AJAX: клик по бейджу переключает отметку — Был → Не был → ... → пусто."""
    project = services.lead_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method != 'POST':
        raise Http404
    member = get_object_or_404(
        _own_direction_eligible_members(request, group)
        .filter(intern__isnull=False), intern_id=request.POST.get('intern'),
    )
    member.mark = attendance_services.toggle_mark(meeting, member.intern, user=request.user)
    return render(request, 'lead_portal/partials/mark_row.html', {
        'project': project, 'meeting': meeting, 'member': member,
    })


@login_required
def meeting_mark_all(request, pk, meeting_pk):
    project = services.lead_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method == 'POST':
        created = attendance_services.mark_all_present(
            meeting, user=request.user, only_role=services.lead_own_role(request.user),
        )
        messages.success(request, f'Отмечено присутствующих: {created}.')
    return redirect('lead_portal:meeting_detail', pk=project.pk, meeting_pk=meeting.pk)


@login_required
def meeting_score(request, pk, meeting_pk):
    """Клик по шкале «Активность» — балл (0–10) или комментарий за период."""
    project = services.lead_project_or_404(request.user, pk)
    group = _group_or_404(project)
    meeting = get_object_or_404(GroupMeeting, pk=meeting_pk, group=group)
    if request.method != 'POST':
        raise Http404
    member = get_object_or_404(
        _own_direction_eligible_members(request, group)
        .select_related('intern__specialization').filter(intern__isnull=False),
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
    return render(request, 'lead_portal/partials/score_row.html', {
        'project': project, 'meeting': meeting, 'member': member,
    })


@login_required
def intern_detail(request, pk, intern_pk):
    """Детальная карточка стажёра — только по своей команде и своему
    направлению, только чтение."""
    project = services.lead_project_or_404(request.user, pk)
    own_role = services.lead_own_role(request.user)
    member = get_object_or_404(
        TeamMember.objects.select_related('intern__specialization'),
        project=project, intern_id=intern_pk, status=TeamMember.Status.ACTIVE,
        role=own_role,
    )
    intern = member.intern
    group = getattr(project, 'group', None)
    scores = (
        WorkScore.objects.filter(intern=intern, meeting__group=group)
        .select_related('meeting').order_by('-meeting__date')
        if group else WorkScore.objects.none()
    )
    values = [item.score for item in scores]
    return render(request, 'lead_portal/intern_detail.html', {
        'project': project, 'member': member, 'intern': intern,
        'scores': scores,
        'average_score': round(sum(values) / len(values), 1) if values else None,
    })


def _team_url(project):
    return f"{reverse('lead_portal:project_detail', args=[project.pk])}?tab=team"


@login_required
def profile_link_create(request, pk):
    """Ссылка на анкету для новых стажёров этого проекта.

    Тимлид отправляет её тем, с кем договорился: кто заполнит анкету,
    сразу окажется в команде проекта. Новая ссылка гасит прежнюю
    ссылку этого же проекта, ссылки других проектов не трогает.
    """
    from apps.interns.services import issue_profile_form_link

    project = services.lead_project_or_404(request.user, pk)
    if request.method == 'POST':
        raw_ttl = request.POST.get('ttl_days', '')
        ttl_days = int(raw_ttl) if raw_ttl.isdigit() else None
        issue_profile_form_link(request.user, ttl_days, project=project)
        messages.success(
            request,
            'Ссылка на анкету готова — отправьте её новому стажёру. '
            'Прежняя ссылка этого проекта больше не открывается.',
        )
    return redirect(_team_url(project))


@login_required
def profile_link_disable(request, pk):
    from apps.interns.services import active_profile_form_link

    project = services.lead_project_or_404(request.user, pk)
    if request.method == 'POST':
        link = active_profile_form_link(project)
        if link is not None:
            link.deactivate()
            messages.success(request, 'Ссылка на анкету отключена.')
    return redirect(_team_url(project))
