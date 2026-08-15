from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.flows.models import Group
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams import services
from apps.teams.forms import TeamMemberForm
from apps.teams.models import TeamMember

User = get_user_model()


@login_required
def team_overview(request):
    """Страница «Команды»: люди и их суммарная загрузка (ТЗ §11)."""
    people = []
    memberships = (
        TeamMember.objects.filter(status=TeamMember.Status.ACTIVE)
        .select_related('project', 'user', 'intern')
    )
    by_person: dict[tuple, list[TeamMember]] = {}
    for member in memberships:
        key = ('u', member.user_id) if member.user_id else ('i', member.intern_id)
        by_person.setdefault(key, []).append(member)
    for member_list in by_person.values():
        first = member_list[0]
        total = sum(m.workload for m in member_list)
        band, band_label = services.workload_band(total)
        people.append({
            'name': first.person_name,
            'is_intern': first.intern_id is not None,
            'total': total,
            'band': band,
            'band_label': band_label,
            'memberships': member_list,
        })
    people.sort(key=lambda person: -person['total'])
    return render(request, 'teams/overview.html', {'people': people})


@login_required
def member_add(request, project_pk):
    """Добавление участника через карточку проекта (команда = группа проекта)."""
    project = get_object_or_404(Project, pk=project_pk)
    group = getattr(project, 'group', None)
    form = TeamMemberForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.project = project
        member.group = group
        member.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        messages.success(request, f'{member.person_name} добавлен(а) в команду.')
        return redirect(f'{project.get_absolute_url()}?tab=team')
    return render(
        request, 'teams/member_form.html',
        {'form': form, 'project': project, 'group': group,
         'title': 'Добавить участника'},
    )


@login_required
def member_add_to_group(request, group_pk):
    """Добавление участника в группу потока."""
    group = get_object_or_404(
        Group.objects.select_related('project', 'flow'), pk=group_pk,
    )
    form = TeamMemberForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.group = group
        member.project = group.project
        member.save()
        warning = form.overload_warning()
        if warning:
            messages.warning(request, warning)
        messages.success(request, f'{member.person_name} добавлен(а) в группу.')
        return redirect(group.get_absolute_url())
    return render(
        request, 'teams/member_form.html',
        {'form': form, 'group': group, 'project': group.project,
         'title': f'Добавить участника в группу {group.code}'},
    )


@login_required
def member_edit(request, pk):
    member = get_object_or_404(
        TeamMember.objects.select_related('project', 'group'), pk=pk,
    )
    form = TeamMemberForm(request.POST or None, instance=member)
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
            'title': f'Редактирование: {member.person_name}',
        },
    )
