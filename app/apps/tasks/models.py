from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.common.models import ArchivableModel, TimeStampedModel
from apps.projects.models import Project, ProjectStage


class TaskStatus(models.TextChoices):
    NEW = 'new', 'Новая'
    IN_PROGRESS = 'in_progress', 'В работе'
    REVIEW = 'review', 'На проверке'
    DONE = 'done', 'Выполнена'
    CANCELLED = 'cancelled', 'Отменена'


class TaskPriority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class Task(TimeStampedModel, ArchivableModel):
    """Задача (ТЗ §10). Может относиться к проекту, этапу или быть личной."""

    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='tasks',
        verbose_name='Проект', null=True, blank=True,
    )
    stage = models.ForeignKey(
        ProjectStage, on_delete=models.SET_NULL, related_name='tasks',
        verbose_name='Этап', null=True, blank=True,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='assigned_tasks', verbose_name='Исполнитель',
        null=True, blank=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='authored_tasks', verbose_name='Автор',
        null=True, blank=True,
    )
    priority = models.CharField(
        'Приоритет', max_length=20,
        choices=TaskPriority.choices, default=TaskPriority.MEDIUM, db_index=True,
    )
    status = models.CharField(
        'Статус', max_length=20,
        choices=TaskStatus.choices, default=TaskStatus.NEW, db_index=True,
    )
    deadline = models.DateField('Deadline', null=True, blank=True, db_index=True)
    completed_at = models.DateField('Дата завершения', null=True, blank=True)

    class Meta:
        verbose_name = 'Задача'
        verbose_name_plural = 'Задачи'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'deadline'])]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse('tasks:detail', args=[self.pk])

    @property
    def is_open(self) -> bool:
        return self.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)


class TaskComment(TimeStampedModel):
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name='comments',
        verbose_name='Задача',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Автор', null=True,
    )
    text = models.TextField('Комментарий')

    class Meta:
        verbose_name = 'Комментарий задачи'
        verbose_name_plural = 'Комментарии задач'
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'Комментарий к «{self.task}»'


class TaskAttachment(TimeStampedModel):
    task = models.ForeignKey(
        Task, on_delete=models.CASCADE, related_name='attachments',
        verbose_name='Задача',
    )
    file = models.FileField('Файл', upload_to='tasks/%Y/%m/')
    name = models.CharField('Название', max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Загрузил', null=True,
    )

    class Meta:
        verbose_name = 'Вложение задачи'
        verbose_name_plural = 'Вложения задач'

    def __str__(self) -> str:
        return self.name or self.file.name


class TaskTemplate(models.Model):
    """Шаблон автоматической задачи (ТЗ §10.1). Настраивается через админку."""

    class Kind(models.TextChoices):
        PROJECT_NEW = 'project_new', 'Новый проект'
        DELIVERY = 'delivery', 'Сдача проекта'

    kind = models.CharField('Событие', max_length=20, choices=Kind.choices)
    title = models.CharField('Название задачи', max_length=255)
    order = models.PositiveSmallIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Активен', default=True)

    class Meta:
        verbose_name = 'Шаблон задачи'
        verbose_name_plural = 'Шаблоны задач'
        ordering = ['kind', 'order']

    def __str__(self) -> str:
        return f'{self.get_kind_display()}: {self.title}'
