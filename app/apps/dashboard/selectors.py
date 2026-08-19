"""Данные для Dashboard (ТЗ §5): KPI-карточки, «Требует внимания», «Сегодня»."""
import datetime

from django.urls import reverse
from django.utils import timezone

from apps.interns.models import Intern, WORKING_STATUSES
from apps.projects import selectors as project_selectors
from apps.projects.models import ProjectStageKey, ProjectStatus
from apps.tasks import selectors as task_selectors
from apps.tasks.models import TaskPriority
from apps.teams.models import TeamMember


def kpi_cards() -> list[dict]:
    """KPI-карточки (ТЗ §5.1). Каждая кликабельна и ведёт на фильтр."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    active = project_selectors.active_projects()
    overdue = project_selectors.overdue_projects(today)
    at_risk = project_selectors.at_risk_projects(today)
    behind = project_selectors.behind_projects(today)
    problem_ids = set(overdue.values_list('pk', flat=True))
    problem_ids |= set(at_risk.values_list('pk', flat=True))
    problem_ids |= set(behind.values_list('pk', flat=True))
    on_track_count = active.exclude(pk__in=problem_ids).count()

    projects_url = reverse('projects:list')
    return [
        {
            'label': 'Активные проекты', 'value': active.count(),
            'url': f'{projects_url}?status=active', 'tone': 'info',
        },
        {
            'label': 'По графику', 'value': on_track_count,
            'url': f'{projects_url}?status=active', 'tone': 'green',
        },
        {
            'label': 'Риск задержки', 'value': at_risk.count(),
            'url': f'{projects_url}?deadline=at_risk', 'tone': 'yellow',
        },
        {
            'label': 'Отставание', 'value': behind.count(),
            'url': f'{projects_url}?deadline=behind', 'tone': 'orange',
        },
        {
            'label': 'Просроченные', 'value': overdue.count(),
            'url': f'{projects_url}?deadline=overdue', 'tone': 'red',
        },
        {
            'label': 'На сдаче',
            'value': active.filter(current_stage=ProjectStageKey.DELIVERY).count(),
            'url': f'{projects_url}?view=delivery', 'tone': 'info',
        },
        {
            'label': 'Завершено за месяц',
            'value': project_selectors.projects_qs().filter(
                status=ProjectStatus.COMPLETED,
                actual_end_date__gte=month_start,
            ).count(),
            'url': reverse('projects:list_completed'), 'tone': 'green',
        },
        {
            'label': 'Активные стажёры',
            'value': Intern.objects.active().filter(
                status__in=WORKING_STATUSES,
            ).count(),
            'url': reverse('interns:list'), 'tone': 'info',
        },
    ]


def attention_items() -> list[dict]:
    """Блок «Требует внимания» (ТЗ §5.2). Каждый warning ведёт на объект."""
    today = timezone.localdate()
    items = []

    for project in project_selectors.overdue_projects(today):
        days = (today - project.planned_end_date).days
        items.append({
            'level': 'red',
            'text': f'{project.name} — просрочен на {days} дн.',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.behind_projects(today):
        items.append({
            'level': 'orange',
            'text': f'{project.name} — отставание '
                    f'(прогресс {project.progress}%, deadline {project.planned_end_date:%d.%m})',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.at_risk_projects(today):
        items.append({
            'level': 'yellow',
            'text': f'{project.name} — риск задержки '
                    f'(прогресс {project.progress}%, deadline {project.planned_end_date:%d.%m})',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.active_projects().filter(
        contract_date__isnull=True,
    ):
        items.append({
            'level': 'yellow',
            'text': f'{project.name} — нет договора',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.inactive_projects():
        items.append({
            'level': 'yellow',
            'text': f'{project.name} — нет обновлений более 3 дней',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.projects_without_pm():
        items.append({
            'level': 'orange',
            'text': f'{project.name} — не назначен ПМ',
            'url': project.get_absolute_url(),
        })
    for project in project_selectors.projects_without_leads():
        items.append({
            'level': 'orange',
            'text': f'{project.name} — не назначены тимлиды',
            'url': project.get_absolute_url(),
        })

    # Delivery без обязательных документов (ТЗ §22: Missing Document)
    from apps.documents import services as doc_services
    for project in project_selectors.active_projects().filter(
        current_stage=ProjectStageKey.DELIVERY,
    ):
        progress = doc_services.document_progress(project)
        if progress['missing']:
            names = ', '.join(t.name for t in progress['missing'])
            items.append({
                'level': 'red',
                'text': f'{project.name} — на сдаче, но нет документов: {names}',
                'url': f'{project.get_absolute_url()}?tab=documents',
            })

    # Просроченные и критические задачи
    for task in task_selectors.overdue_tasks(today)[:10]:
        items.append({
            'level': 'red',
            'text': f'Задача просрочена: {task.title}'
                    + (f' ({task.project.name})' if task.project else ''),
            'url': task.get_absolute_url(),
        })
    for task in task_selectors.open_tasks().filter(
        priority=TaskPriority.CRITICAL,
    )[:10]:
        items.append({
            'level': 'orange',
            'text': f'Critical задача: {task.title}'
                    + (f' ({task.project.name})' if task.project else ''),
            'url': task.get_absolute_url(),
        })

    # Перегруженные люди (ТЗ §22: загрузка > 100%)
    workload_by_person: dict[tuple, dict] = {}
    for member in TeamMember.objects.filter(
        status=TeamMember.Status.ACTIVE,
    ).select_related('user', 'intern'):
        key = ('u', member.user_id) if member.user_id else ('i', member.intern_id)
        entry = workload_by_person.setdefault(
            key, {'name': member.person_name, 'total': 0},
        )
        entry['total'] += member.workload
    for entry in workload_by_person.values():
        if entry['total'] > 100:
            items.append({
                'level': 'orange',
                'text': f'{entry["name"]} — перегруз ({entry["total"]}%)',
                'url': reverse('teams:overview'),
            })

    order = {'red': 0, 'orange': 1, 'yellow': 2}
    items.sort(key=lambda item: order.get(item['level'], 3))
    return items


def today_items() -> list[dict]:
    """Блок «Сегодня» (ТЗ §5.3): дедлайны проектов и этапов."""
    today = timezone.localdate()
    items = []
    for project in project_selectors.active_projects().filter(
        planned_end_date=today,
    ):
        items.append({
            'text': f'Сдача проекта: {project.name}',
            'url': project.get_absolute_url(),
        })
    for task in task_selectors.open_tasks().filter(deadline=today):
        items.append({
            'text': f'Задача на сегодня: {task.title}',
            'url': task.get_absolute_url(),
        })
    week_end = today + datetime.timedelta(days=7)
    for project in project_selectors.active_projects().filter(
        planned_end_date__gt=today, planned_end_date__lte=week_end,
    ).order_by('planned_end_date'):
        items.append({
            'text': f'{project.planned_end_date:%d.%m} — deadline: {project.name}',
            'url': project.get_absolute_url(),
        })
    return items
