from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.projects.forms import (
    ProjectAboutForm,
    ProjectAccessForm,
    ProjectClientForm,
    ProjectDatesForm,
    ProjectDetailsForm,
    ProjectForm,
    ProjectLinksForm,
    ProjectProgressForm,
    StageUpdateForm,
)
from apps.projects.models import (
    Project,
    ProjectAccess,
    ProjectStage,
    ProjectStageKey,
    ProjectStatus,
    ProjectStatusHistory,
    ProjectType,
)
from apps.projects import selectors, services


# Категории списка проектов — отдельные страницы (не query-фильтры)
PROJECT_CATEGORIES = {
    'all': {'title': 'Все проекты', 'statuses': None},
    'in_progress': {
        'title': 'Проекты в процессе',
        'statuses': [ProjectStatus.ACTIVE, ProjectStatus.PAUSED],
    },
    'rejected': {
        'title': 'Отклонённые проекты',
        'statuses': [ProjectStatus.CANCELLED, ProjectStatus.REFUSED],
    },
    'completed': {
        'title': 'Завершённые проекты',
        'statuses': [ProjectStatus.COMPLETED],
    },
}


@login_required
def project_list(request, category='all'):
    config = PROJECT_CATEGORIES[category]
    qs = selectors.filter_projects(selectors.projects_qs(), request.GET)
    if config['statuses']:
        qs = qs.filter(status__in=config['statuses'])
    # Переход со «На сдаче» на dashboard
    if request.GET.get('view') == 'delivery':
        qs = qs.filter(
            current_stage=ProjectStageKey.DELIVERY, status=ProjectStatus.ACTIVE,
        )

    per_page = request.GET.get('per_page', '25')
    if per_page not in ('25', '50', '100'):
        per_page = '25'
    paginator = Paginator(qs, int(per_page))
    page = paginator.get_page(request.GET.get('page'))
    selectors.annotate_deadline_statuses(page.object_list)

    context = {
        'page': page,
        'category': category,
        'title': config['title'],
        'show_status_filter': config['statuses'] is None,
        'project_types': ProjectType.objects.all(),
        'cities': Project.objects.active()
                  .exclude(city='').values_list('city', flat=True)
                  .distinct().order_by('city'),
        'flows': Project.objects.active()
                 .exclude(flow__isnull=True).values_list('flow', flat=True)
                 .distinct().order_by('-flow'),
        'statuses': ProjectStatus.choices,
        'stages': ProjectStageKey.choices,
        'params': request.GET,
    }
    return render(request, 'projects/list.html', context)


@login_required
def project_kanban(request):
    """Pipeline: проекты по этапам (ТЗ §6.4). Drag-and-drop через HTMX."""
    projects = selectors.annotate_deadline_statuses(
        selectors.active_projects().order_by('planned_end_date'),
    )
    columns = []
    for key, label in ProjectStageKey.choices:
        if key == ProjectStageKey.COMPLETED:
            continue
        columns.append({
            'key': key,
            'label': label,
            'projects': [p for p in projects if p.current_stage == key],
        })
    return render(request, 'projects/kanban.html', {'columns': columns})


@login_required
def project_move_stage(request, pk):
    """Endpoint для drag-and-drop в Kanban: двигает проект между этапами."""
    if request.method != 'POST':
        return redirect('projects:kanban')
    project = get_object_or_404(Project.objects.active(), pk=pk)
    stage_key = request.POST.get('stage')
    if stage_key in ProjectStageKey.values:
        services.move_project_to_stage(project, stage_key, user=request.user)
    return HttpResponse(status=204)


@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        Project.objects.select_related(
            'client', 'project_type', 'project_manager', 'team_lead',
        ),
        pk=pk,
    )
    project.deadline_status = services.calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {
        'project': project,
        'tab': tab,
        'stages': project.stages.select_related('responsible'),
        'history': project.history.select_related('user')[:50],
        'today': timezone.localdate(),
    }
    if tab == 'tasks':
        from apps.tasks.models import TaskStatus
        context['tasks'] = (
            project.tasks.active().select_related('assignee', 'project')
        )
        context['task_statuses'] = TaskStatus.choices
    elif tab == 'team':
        context['team_members'] = (
            project.team_members.select_related('user', 'intern')
        )
    elif tab == 'access':
        context['accesses'] = project.accesses.all()
        context['access_form'] = ProjectAccessForm()
    elif tab == 'documents':
        from apps.documents import services as doc_services
        context['documents'] = (
            project.documents.active().select_related('doc_type')
        )
        context['doc_progress'] = doc_services.document_progress(project)
    elif tab == 'delivery':
        from apps.projects import delivery
        context['delivery_checks'] = delivery.delivery_checks(project)
        context['delivery_ready'] = not delivery.failed_checks(project)
    return render(request, 'projects/detail.html', context)


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        project = form.save(commit=False)
        services.create_project(project, user=request.user)
        messages.success(request, f'Проект «{project.name}» создан.')
        return redirect(project.get_absolute_url())
    return render(
        request, 'projects/form.html',
        {'form': form, 'title': 'Новый проект'},
    )


@login_required
def project_update(request, pk):
    project = get_object_or_404(Project, pk=pk)
    old_values = {
        field: getattr(project, field) for field in services.TRACKED_FIELDS
    }
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        services.update_project(
            updated, old_values, user=request.user,
            reason=form.cleaned_data.get('change_reason', ''),
        )
        messages.success(request, 'Проект обновлён.')
        return redirect(updated.get_absolute_url())
    return render(
        request, 'projects/form.html',
        {'form': form, 'title': f'Редактирование: {project.name}', 'project': project},
    )


@login_required
def project_complete(request, pk):
    """Кнопка «Завершить проект» (ТЗ §18): проверяет условия сдачи."""
    from apps.projects import delivery
    project = get_object_or_404(Project, pk=pk)
    if request.method != 'POST':
        return redirect(f'{project.get_absolute_url()}?tab=delivery')
    force = request.POST.get('force') == '1'
    reason = request.POST.get('reason', '').strip()
    if force and not reason:
        messages.error(
            request, 'Принудительное завершение требует указания причины.',
        )
        return redirect(f'{project.get_absolute_url()}?tab=delivery')
    success, failed = delivery.complete_project(
        project, user=request.user, force=force, reason=reason,
    )
    if success:
        messages.success(request, f'Проект «{project.name}» завершён.')
    else:
        details = '; '.join(check['label'] for check in failed)
        messages.error(request, f'Нельзя завершить проект. Не выполнено: {details}.')
    return redirect(f'{project.get_absolute_url()}?tab=delivery')


# Инлайн-редактирование панелей карточки проекта (AJAX через HTMX)
PROJECT_SECTIONS = {
    'progress': ProjectProgressForm,
    'client': ProjectClientForm,
    'links': ProjectLinksForm,
    'about': ProjectAboutForm,
    'details': ProjectDetailsForm,
    'dates': ProjectDatesForm,
}


@login_required
def project_section(request, pk, section):
    """Отдаёт панель обзора: в режиме просмотра или редактирования.

    GET  ?edit=1 — форма панели, GET — просмотр, POST — сохранение.
    Каждая панель редактируется отдельно, без общей формы проекта.
    """
    if section not in PROJECT_SECTIONS:
        raise Http404
    project = get_object_or_404(
        Project.objects.select_related(
            'client', 'project_type', 'project_manager', 'team_lead',
        ),
        pk=pk,
    )
    form_class = PROJECT_SECTIONS[section]
    view_template = f'projects/partials/section_{section}.html'
    form_template = f'projects/partials/section_{section}_form.html'

    if request.method == 'POST':
        old_values = {
            field: getattr(project, field) for field in services.TRACKED_FIELDS
        }
        form = form_class(request.POST, instance=project)
        if form.is_valid():
            updated = form.save(commit=False)
            services.update_project(
                updated, old_values, user=request.user,
                reason=form.cleaned_data.get('change_reason', ''),
            )
            if hasattr(form, 'save_client'):
                form.save_client()
            project.refresh_from_db()
            project.deadline_status = services.calculate_deadline_status(project)
            return render(request, view_template, {'project': project})
        return render(request, form_template, {'form': form, 'project': project})

    if request.GET.get('edit'):
        return render(
            request, form_template,
            {'form': form_class(instance=project), 'project': project},
        )
    project.deadline_status = services.calculate_deadline_status(project)
    return render(request, view_template, {'project': project})


@login_required
def access_create(request, pk):
    """Добавление доступа (логин/пароль) в карточку проекта."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        form = ProjectAccessForm(request.POST)
        if form.is_valid():
            access = form.save(commit=False)
            access.project = project
            access.save()
            ProjectStatusHistory.objects.create(
                project=project, field='Доступы',
                new_value=f'Добавлен доступ: {access.service}',
                user=request.user,
            )
            messages.success(request, f'Доступ «{access.service}» добавлен.')
        else:
            messages.error(request, 'Не удалось сохранить доступ — проверьте поля.')
    return redirect(f'{project.get_absolute_url()}?tab=access')


@login_required
def access_update(request, pk):
    access = get_object_or_404(
        ProjectAccess.objects.select_related('project'), pk=pk,
    )
    form = ProjectAccessForm(request.POST or None, instance=access)
    if request.method == 'POST' and form.is_valid():
        form.save()
        ProjectStatusHistory.objects.create(
            project=access.project, field='Доступы',
            new_value=f'Изменён доступ: {access.service}',
            user=request.user,
        )
        messages.success(request, 'Доступ обновлён.')
        return redirect(f'{access.project.get_absolute_url()}?tab=access')
    return render(
        request, 'projects/access_form.html',
        {'form': form, 'access': access, 'project': access.project,
         'title': f'Доступ: {access.service}'},
    )


@login_required
def access_delete(request, pk):
    access = get_object_or_404(
        ProjectAccess.objects.select_related('project'), pk=pk,
    )
    project = access.project
    if request.method == 'POST':
        ProjectStatusHistory.objects.create(
            project=project, field='Доступы',
            new_value=f'Удалён доступ: {access.service}',
            user=request.user,
        )
        access.delete()
        messages.success(request, 'Доступ удалён.')
    return redirect(f'{project.get_absolute_url()}?tab=access')


@login_required
def stage_update(request, pk):
    """HTMX endpoint: инлайн-обновление этапа в карточке проекта."""
    stage = get_object_or_404(
        ProjectStage.objects.select_related('project'), pk=pk,
    )
    form = StageUpdateForm(request.POST or None, instance=stage)
    if request.method == 'POST' and form.is_valid():
        updated = form.save()
        services.update_stage(updated, user=request.user)
        return render(
            request, 'projects/partials/stage_row.html',
            {'stage': updated, 'project': updated.project},
        )
    return render(
        request, 'projects/partials/stage_form.html',
        {'form': form, 'stage': stage},
    )
