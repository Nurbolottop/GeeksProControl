"""Delivery workflow (ТЗ §18): 100% прогресса != завершённый проект.

Кнопка «Завершить проект» проверяет обязательные условия и называет
конкретные причины отказа. Head может завершить принудительно —
только с причиной и записью в историю.
"""
import datetime

from django.db import transaction
from django.utils import timezone

from apps.projects.models import (
    Project,
    ProjectStageKey,
    ProjectStatus,
    ProjectStatusHistory,
)


def delivery_checks(project: Project) -> list[dict]:
    """Список проверок готовности к сдаче: [{label, ok, hint}]."""
    from apps.documents import services as doc_services
    from apps.documents.models import CONTRACT, FINAL_ACT, REQUIREMENTS
    from apps.tasks.models import TaskPriority, TaskStatus

    open_statuses = (TaskStatus.NEW, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)
    open_critical = project.tasks.active().filter(
        priority=TaskPriority.CRITICAL, status__in=open_statuses,
    ).count()
    open_tasks = project.tasks.active().filter(status__in=open_statuses).count()

    checks = [
        {
            'group': 'Техническая готовность',
            'label': 'Функционал завершён (прогресс 100%)',
            'ok': project.progress >= 100,
            'hint': f'Текущий прогресс: {project.progress}%',
        },
        {
            'group': 'Техническая готовность',
            'label': 'Production развёрнут',
            'ok': bool(project.production_url),
            'hint': 'Заполните Production URL в карточке проекта',
        },
        {
            'group': 'Техническая готовность',
            'label': 'Домен подключён',
            'ok': bool(project.domain),
            'hint': 'Заполните поле «Домен» в карточке проекта',
        },
        {
            'group': 'Техническая готовность',
            'label': 'Critical bugs = 0',
            'ok': open_critical == 0,
            'hint': f'Открытых critical задач: {open_critical}',
        },
        {
            'group': 'Документы',
            'label': 'Договор имеется',
            'ok': doc_services.has_document(project, CONTRACT),
            'hint': 'Загрузите договор во вкладке «Документы»',
        },
        {
            'group': 'Документы',
            'label': 'ТЗ имеется',
            'ok': doc_services.has_document(project, REQUIREMENTS),
            'hint': 'Загрузите ТЗ во вкладке «Документы»',
        },
        {
            'group': 'Документы',
            'label': 'Акт подготовлен',
            'ok': doc_services.has_document(project, FINAL_ACT),
            'hint': 'Загрузите финальный акт во вкладке «Документы»',
        },
        {
            'group': 'Документы',
            'label': 'Акт подписан',
            'ok': doc_services.has_signed_document(project, FINAL_ACT),
            'hint': 'Отметьте акт подписанным с датой подписания',
        },
        {
            'group': 'Клиент',
            'label': 'Доступы загружены на платформу',
            'ok': project.accesses.exists(),
            'hint': 'Добавьте логины и пароли во вкладке «Доступы»',
        },
        {
            'group': 'Клиент',
            'label': 'Все задачи чек-листа сдачи закрыты',
            'ok': open_tasks == 0,
            'hint': f'Открытых задач по проекту: {open_tasks}',
        },
    ]
    return checks


def failed_checks(project: Project) -> list[dict]:
    return [c for c in delivery_checks(project) if not c['ok']]


@transaction.atomic
def complete_project(
    project: Project, user=None, *, force: bool = False, reason: str = '',
) -> tuple[bool, list[dict]]:
    """Завершает проект. Возвращает (успех, невыполненные проверки).

    При ``force=True`` (только Head) проверки пропускаются,
    но причина обязательна и фиксируется в истории (ТЗ §18.1).
    """
    from apps.teams.models import TeamMember

    failed = failed_checks(project)
    if failed and not force:
        return False, failed
    if force and not reason.strip():
        raise ValueError('Принудительное завершение требует причину.')

    today = timezone.localdate()
    project.status = ProjectStatus.COMPLETED
    project.current_stage = ProjectStageKey.COMPLETED
    project.actual_end_date = today
    project.last_activity_at = timezone.now()
    project.save()

    # Освобождаем команду (ТЗ §42.3)
    project.team_members.filter(status=TeamMember.Status.ACTIVE).update(
        status=TeamMember.Status.LEFT, left_at=today,
    )

    ProjectStatusHistory.objects.create(
        project=project,
        field='Завершение (принудительно)' if force else 'Завершение',
        new_value=f'Проект завершён {today:%d.%m.%Y}',
        reason=reason, user=user,
    )
    from apps.audit.services import log as audit_log
    audit_log(
        project,
        'Принудительное завершение проекта' if force else 'Завершение проекта',
        new_value=f'{today:%d.%m.%Y}', reason=reason, user=user,
    )
    return True, []


def delay_days_on_completion(project: Project) -> int | None:
    """Задержка сдачи относительно плановой даты (для KPI)."""
    if project.planned_end_date and project.actual_end_date:
        return (project.actual_end_date - project.planned_end_date).days
    return None
