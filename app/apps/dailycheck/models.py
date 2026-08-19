from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class CheckItem(TimeStampedModel):
    """Пункт ежедневной проверки: что смотреть с приходом в офис."""

    class Block(models.TextChoices):
        PROJECTS = 'projects', 'Проекты'
        PEOPLE = 'people', 'Люди и команды'
        MEETINGS = 'meetings', 'Собрания и табель'
        OFFICE = 'office', 'Офис и организация'

    title = models.CharField('Пункт', max_length=200)
    hint = models.CharField('Пояснение', max_length=255, blank=True)
    block = models.CharField(
        'Блок', max_length=20,
        choices=Block.choices, default=Block.PROJECTS, db_index=True,
    )
    order = models.PositiveSmallIntegerField('Порядок', default=100)
    is_active = models.BooleanField('Показывать', default=True, db_index=True)

    class Meta:
        verbose_name = 'Пункт проверки'
        verbose_name_plural = 'Пункты ежедневной проверки'
        ordering = ['block', 'order', 'pk']

    def __str__(self) -> str:
        return self.title


class CheckMark(TimeStampedModel):
    """Отметка «проверил» по пункту за конкретный день."""

    date = models.DateField('Дата', db_index=True)
    item = models.ForeignKey(
        CheckItem, on_delete=models.CASCADE, related_name='marks',
        verbose_name='Пункт',
    )
    is_done = models.BooleanField('Проверено', default=True)
    note = models.CharField('Что заметил', max_length=255, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Проверил', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Отметка проверки'
        verbose_name_plural = 'Отметки ежедневной проверки'
        unique_together = [('date', 'item')]
        ordering = ['-date']

    def __str__(self) -> str:
        return f'{self.date:%d.%m.%Y} — {self.item}'


# Что проверяем каждый день — создаётся автоматически при первом заходе
DEFAULT_ITEMS = [
    (CheckItem.Block.PROJECTS, 'Просроченные проекты',
     'Посмотреть, у каких проектов вышел срок, и что с ними делают'),
    (CheckItem.Block.PROJECTS, 'Проекты без движения',
     'Где несколько дней ничего не менялось — узнать причину'),
    (CheckItem.Block.PROJECTS, 'Проекты на сдаче',
     'Что осталось закрыть до подписания акта'),
    (CheckItem.Block.PROJECTS, 'Задачи с дедлайном сегодня',
     'Успевают ли и нужна ли помощь'),
    (CheckItem.Block.MEETINGS, 'Вчерашние собрания отмечены',
     'Все ли ПМ проставили посещаемость'),
    (CheckItem.Block.MEETINGS, 'Собрания на сегодня',
     'Кто с кем и во сколько собирается'),
    (CheckItem.Block.MEETINGS, 'Активность команд',
     'Где баллы просели — разобраться с ПМ'),
    (CheckItem.Block.PEOPLE, 'Кто не вышел',
     'Отсутствующие стажёры — выяснить причину'),
    (CheckItem.Block.PEOPLE, 'Свободные стажёры',
     'Кого можно поставить на проект'),
    (CheckItem.Block.PEOPLE, 'Новые люди',
     'Кто вышел впервые — познакомить с командой'),
    (CheckItem.Block.OFFICE, 'Обход офиса',
     'Бишкек и Ош: рабочие места, техника, порядок'),
    (CheckItem.Block.OFFICE, 'Уведомления в системе',
     'Разобрать непрочитанные'),
]


def ensure_default_items() -> None:
    """Создаёт стандартный набор пунктов, если их ещё нет."""
    if CheckItem.objects.exists():
        return
    CheckItem.objects.bulk_create([
        CheckItem(block=block, title=title, hint=hint, order=(index + 1) * 10)
        for index, (block, title, hint) in enumerate(DEFAULT_ITEMS)
    ])


class ProjectCheckItem(TimeStampedModel):
    """Ежедневный пункт по конкретному проекту.

    Набор у всех проектов одинаковый, но лишнее можно убрать,
    а своё — добавить.
    """

    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='daily_items', verbose_name='Проект',
    )
    title = models.CharField('Пункт', max_length=200)
    hint = models.CharField('Пояснение', max_length=255, blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=100)
    is_active = models.BooleanField('Показывать', default=True, db_index=True)

    class Meta:
        verbose_name = 'Ежедневный пункт проекта'
        verbose_name_plural = 'Ежедневные пункты проектов'
        ordering = ['order', 'pk']

    def __str__(self) -> str:
        return f'{self.project.code}: {self.title}'


class ProjectCheckMark(TimeStampedModel):
    """Отметка по ежедневному пункту проекта за день."""

    date = models.DateField('Дата', db_index=True)
    item = models.ForeignKey(
        ProjectCheckItem, on_delete=models.CASCADE, related_name='marks',
        verbose_name='Пункт',
    )
    is_done = models.BooleanField('Проверено', default=True)
    note = models.CharField('Что заметил', max_length=255, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Проверил', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Отметка по проекту'
        verbose_name_plural = 'Ежедневные отметки по проектам'
        unique_together = [('date', 'item')]
        ordering = ['-date']

    def __str__(self) -> str:
        return f'{self.date:%d.%m.%Y} — {self.item.title}'


# Стартовый набор пунктов для проекта. Пока пуст — состав согласуется.
PROJECT_DEFAULT_ITEMS: list[tuple[str, str]] = []


def ensure_project_items(project) -> None:
    """Разворачивает стандартный набор пунктов для проекта."""
    if ProjectCheckItem.objects.filter(project=project).exists():
        return
    ProjectCheckItem.objects.bulk_create([
        ProjectCheckItem(
            project=project, title=title, hint=hint, order=(index + 1) * 10,
        )
        for index, (title, hint) in enumerate(PROJECT_DEFAULT_ITEMS)
    ])
