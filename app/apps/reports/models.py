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
