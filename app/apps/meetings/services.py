"""Логика собраний: авто-повестка и решения → задачи (ТЗ §19.1, §19.2)."""
from apps.meetings.models import Meeting, MeetingDecision
from apps.tasks.models import Task, TaskPriority


def build_auto_agenda() -> list[str]:
    """Проблемные пункты для повестки: просрочки, риски, critical tasks,
    неактивные проекты, перегруз, близкие сдачи (ТЗ §19.1)."""
    from apps.dashboard.selectors import attention_items
    from apps.projects import selectors as project_selectors
    import datetime

    from django.utils import timezone

    points = [item['text'] for item in attention_items()]
    today = timezone.localdate()
    soon = today + datetime.timedelta(days=7)
    for project in project_selectors.active_projects().filter(
        current_stage='delivery',
    ):
        points.append(f'Близкая сдача: {project.name}')
    for project in project_selectors.active_projects().filter(
        planned_end_date__gte=today, planned_end_date__lte=soon,
    ):
        points.append(
            f'Deadline на неделе: {project.name} ({project.planned_end_date:%d.%m})',
        )
    # Убираем дубли, сохраняя порядок
    return list(dict.fromkeys(points))


def create_task_from_decision(decision: MeetingDecision, user=None) -> Task:
    """Кнопка «Создать задачу» у решения собрания (ТЗ §19.2)."""
    if decision.task:
        return decision.task
    task = Task.objects.create(
        title=decision.text[:250],
        description=f'Решение собрания «{decision.meeting}»',
        project=decision.meeting.project,
        assignee=decision.responsible,
        author=user,
        deadline=decision.deadline,
        priority=TaskPriority.HIGH,
    )
    decision.task = task
    decision.save(update_fields=['task', 'updated_at'])
    return task
