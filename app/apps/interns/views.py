from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.interns import services
from apps.interns.forms import GrantAccessForm, InternEvaluationForm, InternForm
from apps.interns.models import Intern, InternEvaluation, InternStatus
from apps.teams.models import TeamMember
from apps.training.models import Specialization, TrainingGroup


def lead_ids() -> set:
    """Тимлиды — сотрудники на зарплате, в списке стажёров их нет."""
    from apps.teams.selectors import lead_intern_ids

    return lead_intern_ids()


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
    params = request.GET
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
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    if params.get('group'):
        qs = qs.filter(training_group_id=params['group'])
    if params.get('city'):
        qs = qs.filter(city=params['city'])
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
    from apps.resources.services import interns_summary
    context = {
        'page': page,
        'params': params,
        'balance': interns_summary(),
        'specializations': Specialization.objects.all(),
        'groups': TrainingGroup.objects.select_related('specialization'),
        'statuses': InternStatus.choices,
        'cities': Intern.objects.active().exclude(city='')
                  .values_list('city', flat=True).distinct().order_by('city'),
    }
    return render(request, 'interns/list.html', context)


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
    from apps.teams.models import TeamRole
    roles = {m.role for m in active_memberships}
    is_lead = TeamRole.TEAM_LEAD in roles
    is_pm = TeamRole.PROJECT_MANAGER in roles
    if is_lead:
        kind, kind_tone = 'Тимлид направления', 'orange'
    else:
        # ПМ — тоже стажёр, а не отдельная категория: его роль и так
        # видна по проектам ниже и по направлению «PM» в шапке.
        kind, kind_tone = 'Стажёр', 'gray'

    context = {
        'intern': intern,
        'is_lead': is_lead,
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
    }
    return render(request, 'interns/detail.html', context)


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
def grant_pm_access(request, pk):
    """Выдать (или сбросить) доступ ПМа в его портал — логин по телефону."""
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
            user = User(username=username, role=User.Role.PROJECT_MANAGER)
        user.role = User.Role.PROJECT_MANAGER
        user.phone = intern.phone
        user.set_password(password)
        user.save()
        if not intern.user_id:
            intern.user = user
            intern.save(update_fields=['user', 'updated_at'])
        messages.success(request, f'Доступ выдан: логин «{username}».')
        return redirect(intern.get_absolute_url())
    return render(request, 'interns/grant_access_form.html', {
        'form': form, 'intern': intern,
    })
