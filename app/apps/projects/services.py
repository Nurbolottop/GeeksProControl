"""Бизнес-логика проектов (service layer, ТЗ §46)."""
import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.projects.models import (
    DeadlineStatus,
    Project,
    ProjectStage,
    ProjectStageKey,
    ProjectStatus,
    ProjectStatusHistory,
)

# Пороговые значения автоматических проверок (ТЗ §22).
# Выносятся в settings, здесь — значения по умолчанию.
RISK_DAYS = getattr(settings, 'DEADLINE_RISK_DAYS', 7)
RISK_PROGRESS = getattr(settings, 'DEADLINE_RISK_PROGRESS', 70)
HIGH_RISK_DAYS = getattr(settings, 'DEADLINE_HIGH_RISK_DAYS', 3)
HIGH_RISK_PROGRESS = getattr(settings, 'DEADLINE_HIGH_RISK_PROGRESS', 90)
INACTIVE_DAYS = getattr(settings, 'PROJECT_INACTIVE_DAYS', 3)

# Изменения этих полей проекта фиксируются в истории (ТЗ §27).
TRACKED_FIELDS = {
    'status': 'Статус',
    'current_stage': 'Этап',
    'planned_end_date': 'Плановая дата завершения',
    'progress': 'Прогресс',
    'priority': 'Приоритет',
    'project_manager': 'Project Manager',
    'team_lead': 'Team Lead',
}


def calculate_deadline_status(
    project: Project, today: datetime.date | None = None,
) -> str:
    """Статус срока проекта (ТЗ §8): rule-based, без AI.

    По графику / Риск задержки / Отставание / Просрочен / Завершён.
    """
    if project.status == ProjectStatus.COMPLETED:
        return DeadlineStatus.COMPLETED
    if not project.planned_end_date:
        return DeadlineStatus.ON_TRACK

    today = today or timezone.localdate()
    days_left = (project.planned_end_date - today).days

    if days_left < 0:
        return DeadlineStatus.OVERDUE
    if days_left <= HIGH_RISK_DAYS and project.progress < HIGH_RISK_PROGRESS:
        return DeadlineStatus.BEHIND
    if days_left <= RISK_DAYS and project.progress < RISK_PROGRESS:
        return DeadlineStatus.AT_RISK
    return DeadlineStatus.ON_TRACK


@transaction.atomic
def create_project(project: Project, user=None) -> Project:
    """Сохраняет новый проект и создаёт полный набор этапов жизненного цикла."""
    project.last_activity_at = timezone.now()
    project.save()
    stages = [
        ProjectStage(project=project, key=key, order=index)
        for index, key in enumerate(ProjectStageKey.values)
    ]
    ProjectStage.objects.bulk_create(stages)
    ProjectStatusHistory.objects.create(
        project=project, field='created',
        new_value='Проект создан', user=user,
    )
    # Типовой чек-лист нового проекта (ТЗ §10.1)
    from apps.tasks.models import TaskTemplate
    from apps.tasks.services import generate_checklist
    generate_checklist(project, TaskTemplate.Kind.PROJECT_NEW, user=user)
    return project


def _display(project: Project, field: str, value) -> str:
    if value is None or value == '':
        return ''
    if field in ('status', 'current_stage', 'priority'):
        # value — «сырое» значение choices; показываем человекочитаемую метку
        choices = dict(Project._meta.get_field(field).choices)
        return str(choices.get(value, value))
    return str(value)


@transaction.atomic
def update_project(
    project: Project, old_values: dict, user=None, reason: str = '',
) -> Project:
    """Сохраняет проект и пишет в историю изменения отслеживаемых полей."""
    records = []
    for field, label in TRACKED_FIELDS.items():
        old = old_values.get(field)
        new = getattr(project, field)
        if old != new:
            records.append(ProjectStatusHistory(
                project=project, field=label,
                old_value=_display(project, field, old),
                new_value=_display(project, field, new),
                reason=reason, user=user,
            ))
    project.last_activity_at = timezone.now()
    project.save()
    if records:
        ProjectStatusHistory.objects.bulk_create(records)
        from apps.audit.services import log as audit_log
        for record in records:
            audit_log(
                project, f'Изменение: {record.field}',
                old_value=record.old_value, new_value=record.new_value,
                reason=reason, user=user,
            )
    return project


@transaction.atomic
def move_project_to_stage(project: Project, stage_key: str, user=None) -> Project:
    """Перемещение проекта между этапами (Kanban, ТЗ §6.4) с записью в историю."""
    old_stage = project.current_stage
    if old_stage == stage_key:
        return project
    project.current_stage = stage_key
    project.last_activity_at = timezone.now()
    project.save(update_fields=['current_stage', 'last_activity_at', 'updated_at'])
    ProjectStatusHistory.objects.create(
        project=project, field='Этап',
        old_value=dict(ProjectStageKey.choices).get(old_stage, old_stage),
        new_value=dict(ProjectStageKey.choices).get(stage_key, stage_key),
        user=user,
    )
    # При переходе в Delivery — автоматический чек-лист сдачи (ТЗ §10.1)
    if stage_key == ProjectStageKey.DELIVERY:
        from apps.tasks.models import TaskTemplate
        from apps.tasks.services import generate_checklist
        generate_checklist(project, TaskTemplate.Kind.DELIVERY, user=user)
    return project


@transaction.atomic
def update_stage(
    stage: ProjectStage, *, status: str | None = None,
    progress: int | None = None, user=None,
) -> ProjectStage:
    """Обновление этапа с автоматикой дат начала/завершения."""
    if status is not None and status != stage.status:
        stage.status = status
        if status == ProjectStage.Status.IN_PROGRESS and not stage.start_date:
            stage.start_date = timezone.localdate()
        if status == ProjectStage.Status.DONE:
            stage.end_date = timezone.localdate()
            stage.progress = 100
    if progress is not None:
        stage.progress = min(100, max(0, progress))
    stage.save()
    project = stage.project
    project.last_activity_at = timezone.now()
    project.save(update_fields=['last_activity_at', 'updated_at'])
    return stage
