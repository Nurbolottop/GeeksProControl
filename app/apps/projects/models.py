from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.clients.models import Client
from apps.common.models import ArchivableModel, TimeStampedModel


class ProjectType(models.Model):
    """Тип проекта (ТЗ §6.2). Справочник, пополняется через админку."""

    name = models.CharField('Название', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Тип проекта'
        verbose_name_plural = 'Типы проектов'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class ProjectStatus(models.TextChoices):
    """Статус проекта — отдельное понятие от этапа (ТЗ §6.3)."""

    ACTIVE = 'active', 'Активный'
    PAUSED = 'paused', 'Приостановлен'
    CANCELLED = 'cancelled', 'Отменён'
    REFUSED = 'refused', 'Клиент отказался'
    COMPLETED = 'completed', 'Завершён'


class ProjectStageKey(models.TextChoices):
    """Этапы жизненного цикла проекта (ТЗ §6.3)."""

    NEW = 'new', 'Новый'
    DOCUMENTS = 'documents', 'Документы'
    REQUIREMENTS = 'requirements', 'ТЗ'
    TEAM_FORMING = 'team_forming', 'Формирование команды'
    DESIGN = 'design', 'Дизайн'
    DEVELOPMENT = 'development', 'Разработка'
    TESTING = 'testing', 'Тестирование'
    REWORK = 'rework', 'Доработка'
    PRODUCTION = 'production', 'Продакшен'
    DELIVERY = 'delivery', 'Сдача'
    COMPLETED = 'completed', 'Завершён'


class ProjectPriority(models.TextChoices):
    LOW = 'low', 'Низкий'
    MEDIUM = 'medium', 'Средний'
    HIGH = 'high', 'Высокий'
    CRITICAL = 'critical', 'Критический'


class DeadlineStatus(models.TextChoices):
    """Автоматический статус срока (ТЗ §8)."""

    ON_TRACK = 'on_track', 'По графику'
    AT_RISK = 'at_risk', 'Риск задержки'
    BEHIND = 'behind', 'Отставание'
    OVERDUE = 'overdue', 'Просрочен'
    COMPLETED = 'completed', 'Завершён'


class Project(TimeStampedModel, ArchivableModel):
    """Проект — центральная сущность системы (ТЗ §6)."""

    code = models.CharField('Внутренний ID', max_length=20, unique=True, blank=True)
    name = models.CharField('Название', max_length=255)
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name='projects',
        verbose_name='Заказчик', null=True, blank=True,
    )
    city = models.CharField('Город / филиал', max_length=100, blank=True, db_index=True)
    flow = models.PositiveSmallIntegerField(
        'Поток', null=True, blank=True, db_index=True,
    )
    project_type = models.ForeignKey(
        ProjectType, on_delete=models.PROTECT, related_name='projects',
        verbose_name='Тип проекта', null=True, blank=True,
    )
    description = models.TextField('Описание', blank=True)

    contract_date = models.DateField('Дата подписания договора', null=True, blank=True)
    start_date = models.DateField('Дата начала', null=True, blank=True)
    planned_end_date = models.DateField(
        'Плановая дата завершения', null=True, blank=True, db_index=True,
    )
    actual_end_date = models.DateField(
        'Фактическая дата завершения', null=True, blank=True,
    )

    status = models.CharField(
        'Статус', max_length=20,
        choices=ProjectStatus.choices, default=ProjectStatus.ACTIVE, db_index=True,
    )
    current_stage = models.CharField(
        'Текущий этап', max_length=20,
        choices=ProjectStageKey.choices, default=ProjectStageKey.NEW, db_index=True,
    )
    priority = models.CharField(
        'Приоритет', max_length=20,
        choices=ProjectPriority.choices, default=ProjectPriority.MEDIUM,
    )
    progress = models.PositiveSmallIntegerField('Процент готовности', default=0)

    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='managed_projects', verbose_name='Project Manager',
        null=True, blank=True,
    )
    team_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='led_projects', verbose_name='Team Lead',
        null=True, blank=True,
    )
    head_comment = models.TextField('Комментарий руководителя', blank=True)

    github_url = models.URLField('GitHub', blank=True)
    figma_url = models.URLField('Figma', blank=True)
    staging_url = models.URLField('Staging URL', blank=True)
    production_url = models.URLField('Production URL', blank=True)
    domain = models.CharField('Домен', max_length=255, blank=True)

    is_favorite = models.BooleanField('Избранный', default=False)
    last_activity_at = models.DateTimeField('Последняя активность', null=True, blank=True)

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'current_stage']),
        ]

    def __str__(self) -> str:
        return f'{self.code} {self.name}'.strip()

    def save(self, *args, **kwargs):
        if not self.code:
            last_id = Project.objects.aggregate(m=models.Max('id'))['m'] or 0
            self.code = f'GP-{last_id + 1:04d}'
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse('projects:detail', args=[self.pk])

    @property
    def duration_days(self):
        """Продолжительность: факт для завершённых, план для остальных."""
        if self.start_date and self.actual_end_date:
            return (self.actual_end_date - self.start_date).days
        if self.start_date and self.planned_end_date:
            return (self.planned_end_date - self.start_date).days
        return None

    @property
    def delay_days(self):
        """Задержка завершённого проекта относительно плана (в днях)."""
        if self.planned_end_date and self.actual_end_date:
            return (self.actual_end_date - self.planned_end_date).days
        return None


class ProjectStage(TimeStampedModel):
    """Этап конкретного проекта (ТЗ §9)."""

    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Не начато'
        IN_PROGRESS = 'in_progress', 'В работе'
        REVIEW = 'review', 'На проверке'
        DONE = 'done', 'Завершено'
        BLOCKED = 'blocked', 'Заблокировано'

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='stages',
        verbose_name='Проект',
    )
    key = models.CharField('Этап', max_length=20, choices=ProjectStageKey.choices)
    order = models.PositiveSmallIntegerField('Порядок', default=0)
    status = models.CharField(
        'Статус', max_length=20,
        choices=Status.choices, default=Status.NOT_STARTED, db_index=True,
    )
    start_date = models.DateField('Дата начала', null=True, blank=True)
    deadline = models.DateField('Deadline', null=True, blank=True, db_index=True)
    end_date = models.DateField('Дата завершения', null=True, blank=True)
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='responsible_stages', verbose_name='Ответственный',
        null=True, blank=True,
    )
    progress = models.PositiveSmallIntegerField('Прогресс', default=0)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Этап проекта'
        verbose_name_plural = 'Этапы проектов'
        ordering = ['order']
        unique_together = [('project', 'key')]

    def __str__(self) -> str:
        return f'{self.project.code}: {self.get_key_display()}'


class ProjectStatusHistory(TimeStampedModel):
    """История изменений проекта (ТЗ §6.4, §27).

    Логирует изменения статуса, этапа, deadline, PM/TL, progress.
    """

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='history',
        verbose_name='Проект',
    )
    field = models.CharField('Поле', max_length=50)
    old_value = models.CharField('Старое значение', max_length=255, blank=True)
    new_value = models.CharField('Новое значение', max_length=255, blank=True)
    reason = models.TextField('Причина', blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Пользователь', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'История проекта'
        verbose_name_plural = 'История проектов'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.project.code}: {self.field}'


class ProjectAccess(TimeStampedModel):
    """Доступы проекта (ТЗ §18: передача доступов).

    Логины/пароли от админки, хостинга, БД и т.п. — загружаются
    на платформу при выходе в прод или сдаче проекта.
    """

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='accesses',
        verbose_name='Проект',
    )
    service = models.CharField(
        'Сервис', max_length=100,
        help_text='Например: Админка сайта, Хостинг, База данных, Домен',
    )
    url = models.CharField('Адрес / URL', max_length=255, blank=True)
    login = models.CharField('Логин', max_length=255, blank=True)
    password = models.CharField('Пароль', max_length=255, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Доступ проекта'
        verbose_name_plural = 'Доступы проектов'
        ordering = ['service']

    def __str__(self) -> str:
        return f'{self.project.code}: {self.service}'


class ProjectLink(models.Model):
    """Дополнительная ссылка проекта (ТЗ §6.1)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='links',
        verbose_name='Проект',
    )
    title = models.CharField('Название', max_length=100)
    url = models.URLField('Ссылка')

    class Meta:
        verbose_name = 'Ссылка проекта'
        verbose_name_plural = 'Ссылки проектов'

    def __str__(self) -> str:
        return self.title
