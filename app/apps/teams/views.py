from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.flows.models import Group
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams import services
from apps.teams.forms import TeamMemberEditForm, TeamMemberForm
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization


def people_options(form):
    """Список людей для поля с поиском."""
    return [
        {
            'id': person.pk,
            'name': person.full_name,
            'spec': str(person.specialization) if person.specialization_id else '',
        }
        for person in form.fields['intern'].queryset
    ]

User = get_user_model()


@login_required
def team_overview(request):
    """Страница загрузки убрана — данные видны в разделе «Стажёры»."""
    return redirect('resources:forecast')


def _role_from(request):
    """В какое направление добавляют — из ссылки секции команды."""
    role = request.GET.get('role') or request.POST.get('role') or ''
    return role if role in TeamRole.values else None


def _title_for(role) -> str:
    if role == TeamRole.PROJECT_MANAGER:
        return 'Добавить ПМ'
    if role == TeamRole.TEAM_LEAD:
        return 'Добавить тимлида'
    if role:
        return f'Добавить: {dict(TeamRole.choices)[role]}'
    return 'Добавить участника'


def _with_new_person(request, role=None):
    """Если человека нет в базе — заводим его прямо из формы команды."""
    from apps.interns.models import InternStatus
    from apps.teams.forms import SPECIALIZATION_BY_ROLE

    data = request.POST.copy()
    name = data.get('new_person', '').strip()
    if not name:
        return data, None

    spec = None
    raw_spec = data.get('new_spec', '')
    if raw_spec.isdigit():
        spec = Specialization.objects.filter(pk=int(raw_spec)).first()
    if spec is None and role:
        spec = Specialization.objects.filter(
            name=SPECIALIZATION_BY_ROLE.get(role, ''),
        ).first()

    intern, created = Intern.objects.get_or_create(
        full_name=name,
        defaults={'specialization': spec, 'status': InternStatus.ACTIVE},
    )
    if created and spec and not intern.specialization_id:
        intern.specialization = spec
        intern.save(update_fields=['specialization', 'updated_at'])
    data['intern'] = intern.pk
    return data, (intern if created else None)


@login_required
def member_add(request, project_pk):
    """Добавление участника через карточку проекта (команда = группа проекта)."""
    project = get_object_or_404(Project, pk=project_pk)
    group = getattr(project, 'group', None)
    role = _role_from(request)
    form = TeamMemberForm(request.POST or None, role=role)
    created_person = None
    if request.method == 'POST':
        data, created_person = _with_new_person(request, role=role)
        form = TeamMemberForm(data, role=role)
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.project = project
        member.group = group
        member.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        if created_person:
            messages.success(request, f'{created_person} заведён(а) в базе.')
        messages.success(request, f'{member.person_name} добавлен(а) в команду.')
        return redirect(f'{project.get_absolute_url()}?tab=team')
    return render(
        request, 'teams/member_form.html',
        {'form': form, 'project': project, 'group': group,
         'people': people_options(form),
         'specializations': Specialization.objects.order_by('name'),
         'role': role,
         'title': _title_for(role)},
    )


@login_required
def member_add_to_group(request, group_pk):
    """Добавление участника в группу потока."""
    group = get_object_or_404(
        Group.objects.select_related('project', 'flow'), pk=group_pk,
    )
    role = _role_from(request)
    form = TeamMemberForm(request.POST or None, role=role)
    created_person = None
    if request.method == 'POST':
        data, created_person = _with_new_person(request, role=role)
        form = TeamMemberForm(data, role=role)
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.group = group
        member.project = group.project
        member.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        if created_person:
            messages.success(request, f'{created_person} заведён(а) в базе.')
        messages.success(request, f'{member.person_name} добавлен(а) в группу.')
        return redirect(group.get_absolute_url())
    return render(
        request, 'teams/member_form.html',
        {'form': form, 'group': group, 'project': group.project,
         'people': people_options(form),
         'specializations': Specialization.objects.order_by('name'),
         'title': f'Добавить участника в группу {group.code}'},
    )


@login_required
def member_edit(request, pk):
    member = get_object_or_404(
        TeamMember.objects.select_related('project', 'group'), pk=pk,
    )
    form = TeamMemberEditForm(request.POST or None, instance=member)
    if request.method == 'POST' and form.is_valid():
        form.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        messages.success(request, 'Участник обновлён.')
        if member.group_id:
            return redirect(member.group.get_absolute_url())
        return redirect(f'{member.project.get_absolute_url()}?tab=team')
    return render(
        request, 'teams/member_form.html',
        {
            'form': form, 'project': member.project, 'group': member.group,
            'people': people_options(form),
            'specializations': Specialization.objects.order_by('name'),
         'specializations': Specialization.objects.order_by('name'),
            'selected_id': member.intern_id,
            'selected_name': member.person_name,
            'title': f'Редактирование: {member.person_name}',
        },
    )


@login_required
def lead_list(request):
    """Тимлиды направлений: кто где ведёт направление.

    Отдельной базы тимлидов нет — это те же люди из «Стажёров»,
    просто с ролью тимлида в конкретной команде.
    """
    leads = (
        TeamMember.objects.filter(role=TeamRole.TEAM_LEAD)
        .select_related('intern__specialization', 'project')
        .order_by('intern__full_name')
    )
    by_person = {}
    for member in leads:
        entry = by_person.setdefault(member.intern_id, {
            'intern': member.intern,
            'projects': [],
        })
        entry['projects'].append(member)

    return render(request, 'teams/lead_list.html', {
        'rows': list(by_person.values()),
        'total': len(by_person),
        'projects': Project.objects.active().order_by('name'),
        'specializations': Specialization.objects.order_by('name'),
        'people': [
            {
                'id': person.pk,
                'name': person.full_name,
                'spec': str(person.specialization) if person.specialization_id else '',
            }
            for person in Intern.objects.filter(is_archived=False)
            .select_related('specialization').order_by('full_name')
        ],
    })


@login_required
def lead_add(request):
    """Назначить человека тимлидом направления в проекте."""
    if request.method != 'POST':
        return redirect('teams:lead_list')

    project = Project.objects.filter(pk=request.POST.get('project')).first()
    if project is None:
        messages.error(request, 'Выберите проект.')
        return redirect('teams:lead_list')

    data, created_person = _with_new_person(request, role=TeamRole.TEAM_LEAD)
    intern = Intern.objects.filter(pk=data.get('intern')).first()
    if intern is None:
        messages.error(request, 'Выберите человека.')
        return redirect('teams:lead_list')

    member, made = TeamMember.objects.get_or_create(
        project=project, intern=intern,
        defaults={
            'group': getattr(project, 'group', None),
            'role': TeamRole.TEAM_LEAD,
            'status': TeamMember.Status.ACTIVE,
        },
    )
    if not made and member.role != TeamRole.TEAM_LEAD:
        member.role = TeamRole.TEAM_LEAD
        member.save(update_fields=['role', 'updated_at'])
        made = True
    if created_person:
        messages.success(request, f'{created_person} заведён(а) в базе.')
    messages.success(request, (
        f'{intern.full_name} — тимлид в проекте «{project.name}».'
        if made else f'{intern.full_name} уже тимлид в «{project.name}».'
    ))
    return redirect('teams:lead_list')


@login_required
def lead_remove(request, pk):
    """Снять роль тимлида: человек остаётся в базе, участие в проекте — нет."""
    member = get_object_or_404(
        TeamMember.objects.select_related('intern', 'project'), pk=pk,
    )
    if request.method == 'POST':
        name = member.person_name
        project = member.project.name if member.project_id else 'проекте'
        member.delete()
        messages.success(request, f'{name} больше не тимлид в «{project}».')
    return redirect('teams:lead_list')


@login_required
def member_delete(request, pk):
    """Убрать участника из команды. Человек остаётся в базе."""
    member = get_object_or_404(
        TeamMember.objects.select_related('project', 'group'), pk=pk,
    )
    project, group = member.project, member.group
    if request.method == 'POST':
        name = member.person_name
        member.delete()
        messages.success(request, f'{name} убран(а) из команды.')
    if project:
        return redirect(f'{project.get_absolute_url()}?tab=team')
    if group:
        return redirect(group.get_absolute_url())
    return redirect('interns:list')


@login_required
def team_clear(request, project_pk):
    """Расформировать команду проекта: снять всех участников."""
    project = get_object_or_404(Project, pk=project_pk)
    if request.method == 'POST':
        removed = project.team_members.count()
        project.team_members.all().delete()
        messages.success(
            request, f'Команда расформирована, снято участников: {removed}.',
        )
    return redirect(f'{project.get_absolute_url()}?tab=team')
