"""Бизнес-логика проектов (service layer, ТЗ §46)."""
import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.projects.models import (
    AccessRequest,
    DeadlineStatus,
    Project,
    ProjectStage,
    ProjectStageKey,
    ProjectStatus,
    ProjectStatusHistory,
    lifecycle_stages,
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
    if project.status != ProjectStatus.ACTIVE:
        # Приостановлен / отменён / отказ — контроль срока не ведётся
        return ''
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
        for index, key in enumerate(lifecycle_stages(project.project_type))
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
def update_stage(stage: ProjectStage, user=None) -> ProjectStage:
    """Сохранение этапа с автоматикой дат начала и завершения."""
    if stage.status == ProjectStage.Status.IN_PROGRESS and not stage.start_date:
        stage.start_date = timezone.localdate()
    if stage.status == ProjectStage.Status.DONE and not stage.end_date:
        stage.end_date = timezone.localdate()
    if stage.status == ProjectStage.Status.NOT_STARTED:
        stage.start_date = None
        stage.end_date = None
    stage.save()
    _touch_project(stage.project)
    return stage


@transaction.atomic
def complete_stage(stage: ProjectStage, user=None) -> ProjectStage:
    """Завершение этапа: ставит дату завершения и двигает проект дальше."""
    stage.status = ProjectStage.Status.DONE
    stage.end_date = timezone.localdate()
    if not stage.start_date:
        stage.start_date = timezone.localdate()
    stage.save()

    project = stage.project
    ProjectStatusHistory.objects.create(
        project=project, field=f'Этап «{stage.get_key_display()}»',
        new_value='Завершён', user=user,
    )
    # Проект автоматически переходит на следующий незавершённый этап
    next_stage = (
        project.stages.filter(order__gt=stage.order)
        .exclude(status=ProjectStage.Status.DONE)
        .order_by('order').first()
    )
    if next_stage and project.current_stage != next_stage.key:
        move_project_to_stage(project, next_stage.key, user=user)
    else:
        _touch_project(project)
    return stage


@transaction.atomic
def extend_stage_deadline(
    stage: ProjectStage, new_deadline, reason: str, user=None,
) -> ProjectStage:
    """Продление дедлайна этапа. Причина обязательна и пишется в историю."""
    old_deadline = stage.deadline
    stage.deadline = new_deadline
    stage.save(update_fields=['deadline', 'updated_at'])

    ProjectStatusHistory.objects.create(
        project=stage.project,
        field=f'Deadline этапа «{stage.get_key_display()}»',
        old_value=f'{old_deadline:%d.%m.%Y}' if old_deadline else '',
        new_value=f'{new_deadline:%d.%m.%Y}',
        reason=reason, user=user,
    )
    from apps.audit.services import log as audit_log
    audit_log(
        stage.project, f'Продление этапа «{stage.get_key_display()}»',
        old_value=f'{old_deadline:%d.%m.%Y}' if old_deadline else '',
        new_value=f'{new_deadline:%d.%m.%Y}', reason=reason, user=user,
    )
    _touch_project(stage.project)
    return stage


def project_pm(project: Project):
    """ПМ проекта: из команды проекта, иначе из группы потока."""
    member = project.team_members.filter(
        role='pm', status='active', intern__isnull=False,
    ).select_related('intern').first()
    if member:
        return member.intern
    group = getattr(project, 'group', None)
    if group is None:
        return None
    member = group.members.filter(
        role='pm', status='active', intern__isnull=False,
    ).select_related('intern').first()
    return member.intern if member else None


@transaction.atomic
def request_accesses(project: Project, services_list, comment: str = '',
                     user=None) -> list:
    """Создаёт запросы доступа у ПМ и шлёт уведомление."""
    from apps.notifications.services import notify

    pm = project_pm(project)
    created = []
    for service in services_list:
        service = service.strip()[:100]
        if not service:
            continue
        if project.access_requests.filter(
            service=service, status=AccessRequest.Status.PENDING,
        ).exists():
            continue
        created.append(AccessRequest.objects.create(
            project=project, service=service, comment=comment,
            requested_by=user, pm=pm,
        ))
    if created:
        names = ', '.join(item.service for item in created)
        notify(
            f'Запрос доступа: {project.name}',
            description=(
                f'{"ПМ " + pm.full_name if pm else "ПМ не назначен"} — '
                f'нужно выдать: {names}.'
            ),
            url=f'{project.get_absolute_url()}?tab=access',
            dedup_key=f'access-request-{project.pk}-{names[:100]}',
        )
        ProjectStatusHistory.objects.create(
            project=project, field='Доступы',
            new_value=f'Запрошено у ПМ: {names}', user=user,
        )
        _touch_project(project)
    return created


@transaction.atomic
def provide_access(access_request, *, url: str = '', login: str = '',
                   password: str = '', comment: str = '', user=None):
    """ПМ выдал доступ: создаём запись в доступах и закрываем запрос."""
    from apps.projects.models import ProjectAccess

    access = ProjectAccess.objects.create(
        project=access_request.project, service=access_request.service,
        url=url, login=login, password=password, comment=comment,
    )
    access_request.access = access
    access_request.status = AccessRequest.Status.PROVIDED
    access_request.resolved_at = timezone.now()
    access_request.save(update_fields=[
        'access', 'status', 'resolved_at', 'updated_at',
    ])
    ProjectStatusHistory.objects.create(
        project=access_request.project, field='Доступы',
        new_value=f'Выдан доступ по запросу: {access_request.service}',
        user=user,
    )
    _touch_project(access_request.project)
    return access


def decline_access(access_request, reason: str = '', user=None):
    """ПМ не даёт доступ — закрываем запрос с причиной."""
    access_request.status = AccessRequest.Status.DECLINED
    access_request.answer = reason[:255]
    access_request.resolved_at = timezone.now()
    access_request.save(update_fields=[
        'status', 'answer', 'resolved_at', 'updated_at',
    ])
    ProjectStatusHistory.objects.create(
        project=access_request.project, field='Доступы',
        new_value=f'Отказано в доступе: {access_request.service}',
        reason=reason, user=user,
    )
    return access_request


def _touch_project(project: Project) -> None:
    project.last_activity_at = timezone.now()
    project.save(update_fields=['last_activity_at', 'updated_at'])
