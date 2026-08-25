import datetime

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
    ProjectCreateForm,
    ProjectDatesForm,
    ProjectDetailsForm,
    ProjectForm,
    ProjectLinksForm,
    ProjectProgressForm,
    StageExtendForm,
    StageUpdateForm,
)
from apps.projects.models import (
    Project,
    ProjectReport,
    ProjectAccess,
    ProjectStage,
    ProjectStageKey,
    ProjectStatus,
    ProjectStatusHistory,
    ProjectType,
)
from apps.flows.models import Flow
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


def _attach_last_reports(projects) -> None:
    """Подтягивает последний написанный отчёт для каждого проекта на странице.

    Один запрос вместо N+1: берём все отчёты нужных проектов сразу,
    в Python оставляем по одному — самому свежему — на проект.
    """
    ids = [p.pk for p in projects]
    if not ids:
        return
    reports = (
        ProjectReport.objects.filter(project_id__in=ids)
        .order_by('project_id', '-date', '-created_at')
    )
    latest_by_project = {}
    for report in reports:
        latest_by_project.setdefault(report.project_id, report)
    for project in projects:
        project.last_report = latest_by_project.get(project.pk)


@login_required
def project_list(request, category='all'):
    config = PROJECT_CATEGORIES[category]
    qs = selectors.filter_projects(selectors.projects_qs(), request.GET)
    if config['statuses']:
        qs = qs.filter(status__in=config['statuses'])
    elif not request.GET.get('status'):
        # Завершённые и отменённые в общий список не попадают — для них есть
        # страницы «Завершённые» и «Отклонённые»; явный фильтр по статусу
        # это правило переопределяет
        qs = qs.exclude(status__in=[
            ProjectStatus.COMPLETED, ProjectStatus.CANCELLED, ProjectStatus.REFUSED,
        ])
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
    _attach_last_reports(page.object_list)

    context = {
        'page': page,
        'category': category,
        'title': config['title'],
        'show_status_filter': config['statuses'] is None,
        'project_types': ProjectType.objects.all(),
        'cities': Project.objects.active()
                  .exclude(city='').values_list('city', flat=True)
                  .distinct().order_by('city'),
        'flows': Flow.objects.filter(projects__isnull=False).distinct(),
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


def _daily_left(project) -> int:
    """Сколько ежедневных пунктов проекта ещё не отмечено сегодня."""
    from apps.dailycheck.models import ProjectCheckItem, ProjectCheckMark

    total = ProjectCheckItem.objects.filter(
        project=project, is_active=True,
    ).count()
    if not total:
        return 0
    done = ProjectCheckMark.objects.filter(
        item__project=project, item__is_active=True,
        date=timezone.localdate(), is_done=True,
    ).count()
    return max(total - done, 0)


@login_required
def project_detail(request, pk):
    project = get_object_or_404(
        Project.objects.select_related(
            'client', 'project_type',
        ),
        pk=pk,
    )
    project.deadline_status = services.calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {
        'project': project,
        'tab': tab,
        'stages': project.stages.all(),
        'history': project.history.select_related('user')[:50],
        'today': timezone.localdate(),
        'daily_left': _daily_left(project),
    }
    if tab == 'tasks':
        from apps.tasks.models import TaskStatus
        context['tasks'] = (
            project.tasks.active().select_related('assignee', 'project')
        )
        context['task_statuses'] = TaskStatus.choices
    elif tab == 'team':
        from apps.teams import selectors as team_selectors
        members = list(
            project.team_members.select_related(
                'user', 'intern__specialization',
            ),
        )
        context['team_members'] = members
        context['team_sections'] = team_selectors.group_by_role(members)
    elif tab == 'access':
        context['accesses'] = project.accesses.all()
        context['access_form'] = ProjectAccessForm()
    elif tab == 'documents':
        from apps.documents import services as doc_services
        from apps.documents.models import DocumentType
        doc_services.ensure_default_types()
        documents = list(
            project.documents.active().select_related('doc_type'),
        )
        by_type = {}
        for document in documents:
            by_type.setdefault(document.doc_type_id, document)
        # Чек-лист: все типы документов, у каждого — загружен или нет
        context['checklist'] = [
            {'type': doc_type, 'document': by_type.get(doc_type.pk)}
            for doc_type in DocumentType.objects.order_by(
                '-required_for_delivery', 'name',
            )
        ]
        context['documents'] = documents
        context['doc_progress'] = doc_services.document_progress(project)
    elif tab == 'report':
        context['reports'] = project.reports.select_related('author')
    elif tab == 'daily':
        from apps.dailycheck import views as daily_views
        day = daily_views._day(request)
        rows = daily_views.project_rows(project, day)
        done = sum(1 for row in rows if row['is_done'])
        context.update({
            'daily_rows': rows,
            'daily_day': day,
            'daily_done': done,
            'daily_all_done': rows and done >= len(rows),
            'daily_is_today': day == timezone.localdate(),
            'daily_prev': day - datetime.timedelta(days=1),
            'daily_next': day + datetime.timedelta(days=1),
        })
    elif tab == 'overview':
        # Завершение проекта живёт в «Обзоре» — там же его проверки
        from apps.projects import delivery
        checks = delivery.delivery_checks(project)
        failed = [check for check in checks if not check['ok']]
        context['delivery_checks'] = checks
        context['delivery_failed'] = failed
        context['delivery_ready'] = not failed
        context['last_report'] = (
            project.reports.select_related('author').first()
        )
    return render(request, 'projects/detail.html', context)


@login_required
def project_create(request):
    """Новый проект. Заказчика можно завести здесь же, не уходя с формы."""
    from apps.clients.models import Client

    form = ProjectCreateForm(request.POST or None)
    if request.method == 'POST':
        data = request.POST.copy()
        changed = False

        # Заказчика и поток можно завести прямо здесь, не уходя с формы
        new_client = data.get('new_client', '').strip()
        if new_client:
            client, created = Client.objects.get_or_create(
                organization=new_client,
                defaults={'city': data.get('city', '').strip()},
            )
            data['client'] = client.pk
            changed = True
            if created:
                messages.success(request, f'Заказчик «{client}» создан.')

        new_flow = data.get('new_flow', '').strip()
        if new_flow.isdigit():
            flow, created = Flow.objects.get_or_create(
                number=int(new_flow),
                defaults={'status': Flow.Status.ACTIVE},
            )
            data['flow'] = flow.pk
            changed = True
            if created:
                messages.success(request, f'Поток {flow.number} создан.')

        if changed:
            form = ProjectCreateForm(data)
        if form.is_valid():
            project = form.save(commit=False)
            services.create_project(project, user=request.user)
            messages.success(request, f'Проект «{project.name}» создан.')
            return redirect(f'{project.get_absolute_url()}?tab=team')
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
def project_delete(request, pk):
    """Удаление проекта — только POST с подтверждением кодом проекта.

    Вместе с проектом каскадно удаляются его этапы, задачи, отчёты,
    документы, доступы и история. Факт удаления остаётся в журнале аудита.
    """
    from apps.audit.services import log as audit_log

    project = get_object_or_404(Project, pk=pk)
    if request.method != 'POST':
        return redirect(project.get_absolute_url())

    confirm = request.POST.get('confirm_code', '').strip()
    expected = project.display_code or str(project.pk)
    if confirm != expected:
        messages.error(
            request,
            f'Проект не удалён: для подтверждения введите его код «{expected}».',
        )
        return redirect(project.get_absolute_url())

    name = str(project)
    counts = (
        f'этапов {project.stages.count()}, задач {project.tasks.count()}, '
        f'отчётов {project.reports.count()}, документов {project.documents.count()}'
    )
    audit_log(
        project, 'deleted', old_value=counts,
        reason=request.POST.get('reason', ''), user=request.user,
    )
    project.delete()
    messages.success(request, f'Проект «{name}» удалён вместе со связанными данными.')
    return redirect('projects:list')


@login_required
def project_complete(request, pk):
    """Кнопка «Завершить проект» (ТЗ §18): проверяет условия сдачи."""
    from apps.projects import delivery
    project = get_object_or_404(Project, pk=pk)
    if request.method != 'POST':
        return redirect(f'{project.get_absolute_url()}?tab=overview')
    force = request.POST.get('force') == '1'
    reason = request.POST.get('reason', '').strip()
    if force and not reason:
        messages.error(
            request, 'Принудительное завершение требует указания причины.',
        )
        return redirect(f'{project.get_absolute_url()}?tab=overview')
    success, failed = delivery.complete_project(
        project, user=request.user, force=force, reason=reason,
    )
    if success:
        messages.success(request, f'Проект «{project.name}» завершён.')
    else:
        details = '; '.join(check['label'] for check in failed)
        messages.error(request, f'Нельзя завершить проект. Не выполнено: {details}.')
    return redirect(f'{project.get_absolute_url()}?tab=overview')


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
            'client', 'project_type',
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
    """Настройка этапа: статус, дедлайн, комментарий (AJAX)."""
    stage = get_object_or_404(
        ProjectStage.objects.select_related('project'), pk=pk,
    )
    if request.method == 'POST':
        form = StageUpdateForm(request.POST, instance=stage)
        if form.is_valid():
            services.update_stage(form.save(commit=False), user=request.user)
            return _stage_row(request, stage)
        return render(
            request, 'projects/partials/stage_form.html',
            {'form': form, 'stage': stage},
        )
    return render(
        request, 'projects/partials/stage_form.html',
        {'form': StageUpdateForm(instance=stage), 'stage': stage},
    )


@login_required
def stage_complete(request, pk):
    """Кнопка «Завершить» у этапа (AJAX)."""
    stage = get_object_or_404(
        ProjectStage.objects.select_related('project'), pk=pk,
    )
    if request.method == 'POST':
        services.complete_stage(stage, user=request.user)
    return _stage_row(request, stage)


@login_required
def stage_extend(request, pk):
    """Кнопка «Продлить дедлайн»: новая дата и обязательная причина (AJAX)."""
    stage = get_object_or_404(
        ProjectStage.objects.select_related('project'), pk=pk,
    )
    if request.method == 'POST':
        form = StageExtendForm(request.POST)
        if form.is_valid():
            services.extend_stage_deadline(
                stage, form.cleaned_data['deadline'],
                form.cleaned_data['reason'], user=request.user,
            )
            return _stage_row(request, stage)
        return render(
            request, 'projects/partials/stage_extend_form.html',
            {'form': form, 'stage': stage},
        )
    return render(
        request, 'projects/partials/stage_extend_form.html',
        {'form': StageExtendForm(initial={'deadline': stage.deadline}),
         'stage': stage},
    )


@login_required
def stage_row(request, pk):
    """Возврат строки этапа в режим просмотра (кнопка «Отмена»)."""
    stage = get_object_or_404(
        ProjectStage.objects.select_related('project'), pk=pk,
    )
    return _stage_row(request, stage)


def _stage_row(request, stage):
    stage.refresh_from_db()
    return render(
        request, 'projects/partials/stage_row.html',
        {'stage': stage, 'project': stage.project,
         'today': timezone.localdate()},
    )


@login_required
def report_create(request, pk):
    """Новый отчёт по проекту."""
    project = get_object_or_404(Project, pk=pk)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if not text:
            messages.error(request, 'Отчёт пустой — напишите текст.')
            return redirect(f'{project.get_absolute_url()}?tab=report')
        report = ProjectReport.objects.create(
            project=project, text=text, author=request.user,
        )
        ProjectStatusHistory.objects.create(
            project=project, field='Отчёт',
            new_value=f'Отчёт от {report.date:%d.%m.%Y}', user=request.user,
        )
        messages.success(request, f'Отчёт от {report.date:%d.%m.%Y} сохранён.')
    return redirect(f'{project.get_absolute_url()}?tab=report')


@login_required
def report_update(request, pk):
    """Правка отчёта по проекту."""
    report = get_object_or_404(
        ProjectReport.objects.select_related('project'), pk=pk,
    )
    project = report.project
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            report.text = text
            report.save(update_fields=['text', 'updated_at'])
            messages.success(request, 'Отчёт обновлён.')
        else:
            messages.error(request, 'Отчёт пустой — текст не сохранён.')
    return redirect(f'{project.get_absolute_url()}?tab=report')


@login_required
def report_delete(request, pk):
    """Удаление отчёта."""
    report = get_object_or_404(
        ProjectReport.objects.select_related('project'), pk=pk,
    )
    project = report.project
    if request.method == 'POST':
        date = report.date
        report.delete()
        messages.success(request, f'Отчёт от {date:%d.%m.%Y} удалён.')
    return redirect(f'{project.get_absolute_url()}?tab=report')
