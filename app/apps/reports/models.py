from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class WeeklyReport(TimeStampedModel):
    """Недельный отчёт (ТЗ §24.1). Показатели фиксируются в JSON."""

    week_start = models.DateField('Начало недели', unique=True)
    data = models.JSONField('Показатели', default=dict)

    comment = models.TextField('Комментарий руководителя', blank=True)

    class Meta:
        verbose_name = 'Недельный отчёт'
        verbose_name_plural = 'Недельные отчёты'
        ordering = ['-week_start']

    def __str__(self) -> str:
        return f'Неделя с {self.week_start:%d.%m.%Y}'


class MonthlyReport(TimeStampedModel):
    """Месячный отчёт по форме рабочей таблицы. Показатели — в JSON."""

    month_start = models.DateField('Месяц', unique=True)
    data = models.JSONField('Показатели', default=dict)
    comment = models.TextField('Комментарий руководителя', blank=True)

    class Meta:
        verbose_name = 'Месячный отчёт'
        verbose_name_plural = 'Месячные отчёты'
        ordering = ['-month_start']

    def __str__(self) -> str:
        return f'Отчёт за {self.month_start:%m.%Y}'


class KPISnapshot(TimeStampedModel):
    """Снимок KPI за период (ТЗ §25)."""

    class Period(models.TextChoices):
        WEEK = 'week', 'Неделя'
        MONTH = 'month', 'Месяц'

    period_type = models.CharField(
        'Период', max_length=10, choices=Period.choices,
    )
    period_start = models.DateField('Начало периода')
    data = models.JSONField('KPI', default=dict)

    class Meta:
        verbose_name = 'KPI snapshot'
        verbose_name_plural = 'KPI snapshots'
        unique_together = [('period_type', 'period_start')]
        ordering = ['-period_start']

    def __str__(self) -> str:
        return f'{self.get_period_type_display()} с {self.period_start:%d.%m.%Y}'


class WrittenReport(TimeStampedModel):
    """Письменный отчёт руководителя: проблемы и достижения.

    Пишется руками, отдельно от цифр недельного отчёта.
    Дата ставится автоматически днём написания.
    """

    date = models.DateField('Дата', auto_now_add=True, db_index=True)
    problems = models.TextField('Проблемы', blank=True)
    achievements = models.TextField('Достижения', blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Автор', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Письменный отчёт'
        verbose_name_plural = 'Письменные отчёты'
        ordering = ['-date', '-created_at']

    def __str__(self) -> str:
        return f'Письменный отчёт от {self.date:%d.%m.%Y}'
