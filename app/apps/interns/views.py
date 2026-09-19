from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.interns import services
from apps.interns.forms import (
    GrantAccessForm, InternEvaluationForm, InternForm, ProfileApplyForm,
    ResumeBankApplyForm, TalentReserveApplyForm, TalentReserveForm,
)
from apps.interns.models import (
    GraduateStatus, Intern, InternEvaluation, InternStatus, ProfileFormLink,
    ProfileFormSubmission, TalentReserveCandidate,
)
from apps.teams.forms import ROLE_BY_SPECIALIZATION, InternProjectAddForm
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization


def lead_ids() -> set:
    """Тимлиды и ПМ — сотрудники на зарплате, в списке стажёров их нет."""
    from apps.teams.selectors import staff_intern_ids

    return staff_intern_ids()


def _attach_current_projects(interns) -> None:
    """Над каким проектом сейчас работает — один запрос вместо N+1."""
    ids = [i.pk for i in interns]
    if not ids:
        return
    memberships = (
        TeamMember.objects.filter(
            intern_id__in=ids, status=TeamMember.Status.ACTIVE,
            project__isnull=False,
        )
        .select_related('project')
        .order_by('project__name')
    )
    by_intern = {}
    for member in memberships:
        by_intern.setdefault(member.intern_id, []).append(member.project)
    for intern in interns:
        intern.current_projects = by_intern.get(intern.pk, [])


@login_required
def intern_list(request):
    qs = (
        Intern.objects.active()
        .exclude(pk__in=lead_ids())
        .select_related('specialization', 'training_group', 'team_lead')
    )
    unassigned_ids = set(
        Intern.objects.filter(status=InternStatus.WAITING)
        .exclude(
            pk__in=TeamMember.objects.filter(
                status=TeamMember.Status.ACTIVE, intern__isnull=False,
            ).values_list('intern_id', flat=True),
        )
        .values_list('pk', flat=True),
    )
    waiting_count = qs.filter(pk__in=unassigned_ids).count()
    params = request.GET
    if params.get('status') == 'waiting':
        qs = qs.filter(pk__in=unassigned_ids)
    search = params.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(telegram__icontains=search),
        )
    if params.get('specialization'):
        qs = qs.filter(specialization_id=params['specialization'])
    if params.get('city'):
        qs = qs.filter(city=params['city'])
    if params.get('branch') in services.BRANCHES:
        qs = qs.filter(services.branch_filter(params['branch']))
    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    if params.get('availability') == 'free':
        qs = qs.exclude(pk__in=busy_ids)
    elif params.get('availability') == 'busy':
        qs = qs.filter(pk__in=busy_ids)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(params.get('page'))
    for intern in page.object_list:
        intern.is_busy = intern.pk in busy_ids
    _attach_current_projects(page.object_list)
    base_params = params.copy()
    base_params.pop('specialization', None)
    base_params.pop('page', None)
    context = {
        'page': page,
        'params': params,
        'base_qs': base_params.urlencode(),
        'waiting_count': waiting_count,
        'specializations': Specialization.objects.all(),
        'cities': Intern.objects.active().exclude(city='')
                  .values_list('city', flat=True).distinct().order_by('city'),
        'profile_link': services.active_profile_form_link(),
        'profile_link_ttls': PROFILE_LINK_TTL_CHOICES,
        'answers_count': ProfileFormSubmission.objects.count(),
    }
    return render(request, 'interns/list.html', context)


# Сроки жизни ссылки на анкету: значение для формы → подпись
PROFILE_LINK_TTL_CHOICES = [
    ('1', 'Сутки'),
    ('3', '3 дня'),
    ('7', '7 дней'),
    ('30', '30 дней'),
    ('', 'Без срока'),
]


@login_required
def profile_link_create(request):
    """Выпустить новую ссылку на публичную анкету (старая перестаёт работать)."""
    if request.method == 'POST':
        raw_ttl = request.POST.get('ttl_days', '')
        ttl_days = int(raw_ttl) if raw_ttl.isdigit() else None
        link = services.issue_profile_form_link(request.user, ttl_days)
        term = f'на {ttl_days} дн.' if ttl_days else 'без срока'
        messages.success(
            request,
            f'Новая ссылка на анкету создана ({term}), прежняя больше не '
            f'открывается: {request.build_absolute_uri(link.get_absolute_url())}',
        )
    return redirect('interns:list')


@login_required
def profile_link_answers(request):
    """Журнал заполнений анкеты — кто и по какой ссылке её прошёл."""
    submissions = (
        ProfileFormSubmission.objects
        .select_related('intern', 'link__project', 'link__created_by__intern_profile')
        .order_by('-created_at')
    )
    token = request.GET.get('link', '')
    if token:
        submissions = submissions.filter(link__token=token)
    paginator = Paginator(submissions, 50)
    return render(request, 'interns/profile_link_answers.html', {
        'page': paginator.get_page(request.GET.get('page')),
        'links': ProfileFormLink.objects.select_related('project')[:50],
        'token': token,
        'total': paginator.count,
    })


@login_required
def profile_link_disable(request):
    """Отключить действующую ссылку, не выпуская новую."""
    if request.method == 'POST':
        link = services.active_profile_form_link()
        if link is not None:
            link.deactivate()
            messages.success(request, 'Ссылка на анкету отключена.')
    return redirect('interns:list')


@login_required
def by_project(request):
    """Стажёры по проектам: где сколько людей и кого не хватает.

    Считаем действующие членства: один человек может быть сразу на двух
    проектах, поэтому сумма по проектам больше, чем людей на проектах.
    Тимлиды — сотрудники на зарплате, в счёт стажёров не идут, но
    показываем их отдельной строкой, чтобы было видно, кто ведёт команду.
    """
    from apps.projects.models import Project, ProjectStatus
    from apps.teams.models import TeamRole

    leads = lead_ids()
    memberships = (
        TeamMember.objects
        .filter(status=TeamMember.Status.ACTIVE, project__isnull=False)
        .select_related('intern__specialization', 'project', 'user')
    )
    rows = {}
    for member in memberships:
        row = rows.setdefault(member.project_id, {
            'project': member.project, 'interns': [], 'specs': {},
            'pms': [], 'leads': [],
        })
        if member.role == TeamRole.PROJECT_MANAGER:
            row['pms'].append(member.intern or member.user)
        if member.intern_id is None:
            continue
        if member.intern_id in leads or member.role == TeamRole.TEAM_LEAD:
            row['leads'].append(member.intern)
            continue
        row['interns'].append(member.intern)
        spec = member.intern.specialization
        name = spec.name if spec else 'Без направления'
        row['specs'][name] = row['specs'].get(name, 0) + 1

    projects = (
        Project.objects.active()
        .exclude(status__in=[
            ProjectStatus.COMPLETED, ProjectStatus.CANCELLED, ProjectStatus.REFUSED,
        ])
        .select_related('client')
    )
    table = []
    for project in projects:
        row = rows.pop(project.pk, None) or {
            'project': project, 'interns': [], 'specs': {}, 'pms': [], 'leads': [],
        }
        row['specs'] = sorted(row['specs'].items(), key=lambda item: (-item[1], item[0]))
        table.append(row)
    # Команды на уже закрытых проектах, если кого-то забыли снять
    for row in rows.values():
        row['specs'] = sorted(row['specs'].items(), key=lambda item: (-item[1], item[0]))
        row['is_closed'] = True
        table.append(row)
    table.sort(key=lambda row: (-len(row['interns']), row['project'].name))

    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
            project__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    free = (
        Intern.objects.active()
        .exclude(pk__in=leads)
        .exclude(pk__in=busy_ids)
        .select_related('specialization')
        .order_by('full_name')
    )
    return render(request, 'interns/by_project.html', {
        'rows': table,
        'projects_count': sum(1 for row in table if row['interns']),
        'on_projects': len(busy_ids - leads),
        'free': free,
    })


@login_required
def by_branch(request):
    """Стажёры по филиалам: сколько человек в Бишкеке и в Оше.

    Считаем ровно тех же людей, что видно в списке стажёров, чтобы
    цифра совпадала с числом строк при переходе по ней.
    """
    interns = list(
        Intern.objects.active()
        .exclude(pk__in=lead_ids())
        .select_related('specialization'),
    )
    summary = services.branch_summary(interns)
    return render(request, 'interns/by_branch.html', summary)


@login_required
def intern_detail(request, pk):
    intern = get_object_or_404(
        Intern.objects.select_related(
            'specialization', 'training_group', 'team_lead',
        ),
        pk=pk,
    )
    memberships = intern.team_memberships.select_related('project')
    active_memberships = [
        m for m in memberships if m.status == TeamMember.Status.ACTIVE
    ]
    past_memberships = [
        m for m in memberships if m.status == TeamMember.Status.LEFT
    ]
    roles = {m.role for m in active_memberships}
    is_lead = TeamRole.TEAM_LEAD in roles
    is_pm = TeamRole.PROJECT_MANAGER in roles
    was_lead = any(m.role == TeamRole.TEAM_LEAD for m in memberships)
    if is_lead:
        kind, kind_tone = 'Тимлид направления', 'orange'
    elif intern.is_archived and was_lead:
        kind, kind_tone = 'Бывший тимлид', 'gray'
    else:
        # ПМ — тоже стажёр, а не отдельная категория: его роль и так
        # видна по проектам ниже и по направлению «PM» в шапке.
        kind, kind_tone = 'Стажёр', 'gray'

    from apps.audit.models import AuditLog

    history = AuditLog.objects.filter(
        object_type='Intern', object_id=str(intern.pk),
    ).select_related('user').order_by('-created_at')[:20]

    context = {
        'intern': intern,
        'is_lead': is_lead,
        'was_lead': was_lead,
        'kind': kind,
        'kind_tone': kind_tone,
        'lead_projects': [
            m for m in active_memberships if m.role == TeamRole.TEAM_LEAD
        ],
        'active_memberships': active_memberships,
        'past_memberships': past_memberships,
        'projects_count': len(active_memberships) + len(past_memberships),
        'evaluations': intern.evaluations.select_related('project', 'evaluator'),
        'criteria': InternEvaluation.CRITERIA,
        'is_pm': is_pm,
        'history': history,
    }
    return render(request, 'interns/detail.html', context)


@login_required
def intern_project_add(request, pk):
    """Добавить стажёра на проект прямо с его карточки."""
    intern = get_object_or_404(Intern, pk=pk)
    if intern.is_archived:
        messages.error(request, f'{intern.full_name} в архиве — сначала верните из архива.')
        return redirect(intern.get_absolute_url())
    form = InternProjectAddForm(
        request.POST or None, instance=TeamMember(intern=intern),
    )
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.group = getattr(member.project, 'group', None)
        spec = intern.specialization
        member.role = ROLE_BY_SPECIALIZATION.get(
            spec.name if spec else '', TeamRole.OTHER,
        )
        member.joined_at = timezone.localdate()
        member.save()
        update_fields = []
        if intern.status in (InternStatus.WAITING, InternStatus.READY):
            intern.status = InternStatus.ACTIVE
            update_fields.append('status')
        if intern.graduate_status:
            from apps.audit.services import log as audit_log

            audit_log(
                intern, 'Статус выпускника снят',
                old_value=intern.get_graduate_status_display(),
                reason=f'переведён(а) на проект «{member.project.name}»',
                user=request.user,
            )
            intern.graduate_status = ''
            update_fields.append('graduate_status')
        if update_fields:
            intern.save(update_fields=[*update_fields, 'updated_at'])
        messages.success(
            request, f'{intern.full_name} добавлен(а) в «{member.project.name}».',
        )
        return redirect(intern.get_absolute_url())
    return render(request, 'interns/project_add_form.html', {
        'form': form, 'intern': intern,
    })


@login_required
def intern_project_remove(request, pk, member_pk):
    """Убрать стажёра с проекта прямо с его карточки."""
    from apps.teams import services as team_services

    intern = get_object_or_404(Intern, pk=pk)
    member = get_object_or_404(TeamMember, pk=member_pk, intern=intern)
    if request.method == 'POST':
        name = member.project.name if member.project_id else 'проекта'
        team_services.leave_team(member, reason=request.POST.get('left_reason', ''))
        messages.success(request, f'Убран(а) с «{name}».')
    return redirect(intern.get_absolute_url())


@login_required
def intern_create(request):
    form = InternForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        intern = form.save()
        messages.success(request, f'Стажёр {intern.full_name} добавлен(а).')
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/form.html', {'form': form, 'title': 'Новый стажёр'},
    )


@login_required
def intern_update(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    form = InternForm(request.POST or None, instance=intern)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Карточка стажёра обновлена.')
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/form.html',
        {'form': form, 'title': f'Редактирование: {intern.full_name}'},
    )


@login_required
def evaluation_add(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    form = InternEvaluationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.intern = intern
        evaluation.evaluator = request.user
        services.add_evaluation(evaluation)
        messages.success(
            request,
            f'Оценка сохранена. Средний рейтинг: {intern.rating}.',
        )
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/evaluation_form.html',
        {'form': form, 'intern': intern, 'title': f'Оценка: {intern.full_name}'},
    )


@login_required
def intern_archive(request, pk):
    """В архив: человек у нас больше не работает, но история остаётся."""
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == 'POST' and not intern.is_archived:
        closed = services.archive_person(
            intern, user=request.user, reason=request.POST.get('reason', '').strip(),
        )
        note = f' и снят(а) с проектов: {closed}' if closed else ''
        messages.success(request, f'{intern.full_name} в архиве{note}.')
    return redirect(intern.get_absolute_url())


@login_required
def intern_unarchive(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == 'POST' and intern.is_archived:
        services.unarchive_person(intern, user=request.user)
        messages.success(
            request,
            f'{intern.full_name} возвращён(а) из архива. На проекты назначьте заново.',
        )
    return redirect(intern.get_absolute_url())


@login_required
def intern_pause(request, pk):
    """Заморозить стажировку — из табеля посещаемости пропадает, из
    команды проекта нет."""
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == 'POST':
        if services.pause_person(intern, user=request.user):
            messages.success(request, f'Стажировка {intern.full_name} заморожена.')
        else:
            messages.error(request, 'Заморозить можно только активную стажировку.')
    return redirect(intern.get_absolute_url())


@login_required
def intern_unpause(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == 'POST':
        if services.unpause_person(intern, user=request.user):
            messages.success(request, f'Стажировка {intern.full_name} возобновлена.')
        else:
            messages.error(request, 'Возобновить можно только замороженную стажировку.')
    return redirect(intern.get_absolute_url())


@login_required
def intern_delete(request, pk):
    """Удаление человека из базы вместе с участием в командах."""
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == "POST":
        name = intern.full_name
        teams = intern.team_memberships.count()
        intern.delete()
        note = f" и снят(а) с проектов: {teams}" if teams else ""
        messages.success(request, f"{name} удалён(а) из базы{note}.")
        return redirect("interns:list")
    return redirect(intern.get_absolute_url())


@login_required
def _grant_role_access(request, pk, role, title):
    """Выдать (или сбросить) доступ в портал своей роли — логин по телефону.

    Общая логика для ПМ и тимлида: отличается только роль учётки и
    подпись формы, доступ у обоих устроен одинаково (Intern.user).
    """
    from apps.accounts.models import User

    intern = get_object_or_404(Intern, pk=pk)
    initial = {'username': intern.user.username if intern.user else intern.phone}
    form = GrantAccessForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        if intern.user:
            user = intern.user
            user.username = username
        else:
            user = User(username=username)
        user.role = role
        user.phone = intern.phone
        user.set_password(password)
        user.save()
        if not intern.user_id:
            intern.user = user
            intern.save(update_fields=['user', 'updated_at'])
        messages.success(request, f'Доступ выдан: логин «{username}».')
        return redirect(intern.get_absolute_url())
    return render(request, 'interns/grant_access_form.html', {
        'form': form, 'intern': intern, 'title': title,
    })


def grant_pm_access(request, pk):
    """Выдать (или сбросить) доступ ПМа в его портал — логин по телефону."""
    from apps.accounts.models import User

    return _grant_role_access(
        request, pk, User.Role.PROJECT_MANAGER, 'Доступ в портал ПМ',
    )


def grant_lead_access(request, pk):
    """Выдать (или сбросить) доступ тимлида в его портал — логин по телефону."""
    from apps.accounts.models import User

    return _grant_role_access(
        request, pk, User.Role.TEAM_LEAD, 'Доступ в портал тимлида',
    )


def _flagged_list(request, field, title):
    """Банк резюме — включая тимлидов, в отличие от общего списка
    стажёров (там тимлиды — уже «сотрудники»)."""
    people = (
        Intern.objects.active().filter(**{field: True})
        .select_related('specialization').order_by('full_name')
    )
    return render(request, 'interns/flagged_list.html', {
        'people': people, 'title': title,
    })


@login_required
def reserve_list(request):
    """Резерв кадров — отдельный пул, не привязан к карточкам стажёров."""
    candidates = TalentReserveCandidate.objects.active().select_related('specialization')
    return render(request, 'interns/reserve_list.html', {
        'candidates': candidates,
    })


@login_required
def reserve_create(request):
    initial = {
        'full_name': request.GET.get('full_name', ''),
        'phone': request.GET.get('phone', ''),
        'email': request.GET.get('email', ''),
        'city': request.GET.get('city', ''),
    }
    form = TalentReserveForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        candidate = form.save()
        messages.success(request, f'«{candidate.full_name}» добавлен(а) в резерв.')
        return redirect('interns:reserve')
    return render(request, 'interns/reserve_form.html', {
        'form': form, 'title': 'Новый кандидат в резерве',
    })


@login_required
def reserve_update(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    form = TalentReserveForm(request.POST or None, instance=candidate)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Кандидат обновлён.')
        return redirect('interns:reserve')
    return render(request, 'interns/reserve_form.html', {
        'form': form, 'title': f'Резерв: {candidate.full_name}',
    })


@login_required
def reserve_delete(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    if request.method == 'POST':
        name = candidate.full_name
        candidate.delete()
        messages.success(request, f'{name} удалён(а) из резерва.')
    return redirect('interns:reserve')


@login_required
def reserve_set_priority(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    if request.method == 'POST':
        raw = request.POST.get('priority', '')
        if raw.isdigit():
            candidate.priority = int(raw)
            candidate.save(update_fields=['priority', 'updated_at'])
    return redirect('interns:reserve')


@login_required
def resume_bank_list(request):
    return _flagged_list(request, 'in_resume_bank', 'Банк резюме')


@login_required
def graduates_list(request):
    """Выпускники: сначала сводка в числах, по клику на число — сами люди.

    Без параметров показываем сводку по направлениям и проектам. Любой
    фильтр (или `all=1`) открывает список, отфильтрованный по нему.
    """
    people = services.graduated_interns()
    params = request.GET
    filters = {key: params.get(key) for key in GRADUATE_FILTERS if params.get(key)}
    if not filters and not params.get('all'):
        return render(request, 'interns/graduates_summary.html', {
            'total': _graduate_counts(people),
            'by_direction': _graduates_by(people, _direction_key),
            'by_project': _graduates_by(people, _project_key),
        })

    selected = [person for person in people if _graduate_matches(person, filters)]
    return render(request, 'interns/graduates_list.html', {
        'people': selected, 'title': 'Выпускники',
        'GraduateStatus': GraduateStatus,
        'filter_label': _graduate_filter_label(filters, people),
        'total_count': len(people),
    })


GRADUATE_FILTERS = ('specialization', 'project', 'status', 'bank')


def _direction_key(person):
    spec = person.specialization
    return (str(spec.pk), spec.name) if spec else ('none', 'Без направления')


def _project_key(person):
    project = person.graduated_project
    return (str(project.pk), str(project)) if project else ('none', 'Проект не найден')


def _graduate_counts(people) -> dict:
    return {
        'total': len(people),
        'pending': sum(1 for p in people if p.graduate_status == GraduateStatus.PENDING),
        'declined': sum(1 for p in people if p.graduate_status == GraduateStatus.DECLINED),
        'in_bank': sum(1 for p in people if p.in_resume_bank),
        'no_bank': sum(1 for p in people if not p.in_resume_bank),
    }


def _graduates_by(people, key) -> list[dict]:
    """Выпускники, сгруппированные по направлению или проекту, с числами."""
    groups = {}
    for person in people:
        value, label = key(person)
        groups.setdefault(value, {'value': value, 'label': label, 'people': []})
        groups[value]['people'].append(person)
    rows = []
    for group in groups.values():
        dates = [p.graduated_at for p in group['people'] if p.graduated_at]
        rows.append({
            'value': group['value'], 'label': group['label'],
            'graduated_at': max(dates) if dates else None,
            **_graduate_counts(group['people']),
        })
    rows.sort(key=lambda row: (-row['total'], row['label']))
    return rows


def _graduate_matches(person, filters) -> bool:
    if 'specialization' in filters and _direction_key(person)[0] != filters['specialization']:
        return False
    if 'project' in filters and _project_key(person)[0] != filters['project']:
        return False
    if 'status' in filters and person.graduate_status != filters['status']:
        return False
    if filters.get('bank') == 'yes' and not person.in_resume_bank:
        return False
    if filters.get('bank') == 'no' and person.in_resume_bank:
        return False
    return True


def _graduate_filter_label(filters, people) -> str:
    """Человеческое описание фильтра: «Backend · На проверке»."""
    parts = []
    for person in people:
        if 'specialization' in filters and _direction_key(person)[0] == filters['specialization']:
            parts.append(_direction_key(person)[1])
            break
    for person in people:
        if 'project' in filters and _project_key(person)[0] == filters['project']:
            parts.append(_project_key(person)[1])
            break
    if filters.get('status') in GraduateStatus.values:
        parts.append(GraduateStatus(filters['status']).label)
    if filters.get('bank') == 'yes':
        parts.append('В банке резюме')
    elif filters.get('bank') == 'no':
        parts.append('Не заполнили анкету банка резюме')
    return ' · '.join(parts)


@login_required
def graduate_decline(request, pk):
    """ПМ отметил, что выпускник не хочет продолжать стажировку.

    В банк резюме это НЕ добавляет — только меняет статус выпускника.
    Дальше на странице «Выпускники» появляется готовый текст-инструкция
    для самого стажёра: попасть в банк резюме можно только его же руками,
    через публичную анкету.
    """
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == 'POST':
        services.decline_graduate(intern)
        messages.success(
            request,
            f'{intern.full_name}: отмечен(а) как не продолжающий(ая) '
            'стажировку. Ниже — текст для отправки, чтобы попасть в банк резюме.',
        )
    # в сводке текста нет — ведём прямо в список, где он раскрывается
    return redirect(f"{reverse('interns:graduates')}?status={GraduateStatus.DECLINED}")


def resume_bank_apply(request):
    """Публичная анкета «Банк резюме» — без входа в систему.

    По телефону ищем уже существующего стажёра, чтобы не плодить
    дубли, если человек уже есть в базе. Одна анкета на браузер —
    после отправки повторно её не откроешь (защита от спама).
    """
    if request.session.get('resume_bank_submitted'):
        return render(request, 'interns/resume_bank_apply_done.html')
    form = ResumeBankApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        intern = Intern.objects.filter(phone=phone).first()
        if intern is None:
            intern = form.save(commit=False)
        else:
            intern.full_name = form.cleaned_data['full_name']
            intern.email = form.cleaned_data['email']
            intern.specialization = form.cleaned_data['specialization']
        intern.in_resume_bank = True
        intern.save()
        request.session['resume_bank_submitted'] = True
        return render(request, 'interns/resume_bank_apply_done.html')
    return render(request, 'interns/resume_bank_apply.html', {'form': form})


def profile_link_expired(request):
    """Старый постоянный адрес анкеты — только сообщение, что ссылка мертва."""
    return render(request, 'interns/profile_apply_expired.html', status=404)


def profile_apply(request, token):
    """Публичная анкета: стажёр сам заполняет/обновляет свой профиль.

    Открывается только по действующей ссылке (`token`): постоянного
    адреса у анкеты нет, новая ссылка гасит прежние. Если ссылка выпущена
    тимлидом для проекта — человек сразу попадает в его команду.

    Сначала ищем по телефону. У многих текущих записей телефон ещё не
    заполнен (карточку когда-то завели по одному ФИО) — тогда, чтобы не
    плодить дубль, ищем среди записей без телефона точное совпадение по
    имени. Если и это не помогло — считаем человека новым. Одна анкета
    на браузер и ссылку — после отправки повторно её не откроешь
    (защита от спама).
    """
    link = ProfileFormLink.objects.filter(token=token).first()
    if link is None or not link.is_open:
        return render(request, 'interns/profile_apply_expired.html', status=404)
    session_key = f'profile_submitted:{token}'
    if request.session.get(session_key):
        return render(request, 'interns/profile_apply_done.html')
    form = ProfileApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        full_name = form.cleaned_data['full_name']
        intern = Intern.objects.filter(phone=phone).first()
        if intern is None:
            intern = Intern.objects.filter(
                phone='', full_name__iexact=full_name,
            ).first()
        is_new = intern is None
        if is_new:
            intern = form.save(commit=False)
        else:
            for field in ProfileApplyForm.Meta.fields:
                setattr(intern, field, form.cleaned_data[field])
        intern.save()
        ProfileFormLink.objects.filter(pk=link.pk).update(
            submissions=models.F('submissions') + 1,
        )
        ProfileFormSubmission.objects.create(
            link=link, intern=intern, full_name=intern.full_name,
            phone=intern.phone, is_new=is_new,
        )
        if link.project_id:
            services.join_project_from_form(intern, link)
        request.session[session_key] = True
        return render(request, 'interns/profile_apply_done.html')
    return render(request, 'interns/profile_apply.html', {'form': form})


def talent_reserve_apply(request):
    """Публичная анкета «Резерв кадров» — без входа в систему.

    Тот же принцип поиска, что и в анкете профиля: сначала точное
    совпадение по телефону, иначе — по ФИО среди записей без телефона.
    Одна анкета на браузер — после отправки повторно её не откроешь
    (защита от спама).
    """
    if request.session.get('talent_reserve_submitted'):
        return render(request, 'interns/reserve_apply_done.html')
    form = TalentReserveApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        full_name = form.cleaned_data['full_name']
        candidate = TalentReserveCandidate.objects.filter(phone=phone).first()
        if candidate is None:
            candidate = TalentReserveCandidate.objects.filter(
                phone='', full_name__iexact=full_name,
            ).first()
        if candidate is None:
            candidate = form.save(commit=False)
        else:
            for field in TalentReserveApplyForm.Meta.fields:
                setattr(candidate, field, form.cleaned_data[field])
        candidate.save()
        request.session['talent_reserve_submitted'] = True
        return render(request, 'interns/reserve_apply_done.html')
    return render(request, 'interns/reserve_apply.html', {'form': form})
