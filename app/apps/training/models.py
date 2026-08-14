from django.db import models

from apps.common.models import TimeStampedModel


class Specialization(models.Model):
    """Направление (ТЗ §12): Backend, Frontend, UX/UI, Mobile, QA, PM."""

    name = models.CharField('Название', max_length=100, unique=True)

    class Meta:
        verbose_name = 'Направление'
        verbose_name_plural = 'Направления'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class TrainingGroup(TimeStampedModel):
    """Учебная группа (ТЗ §13)."""

    number = models.CharField('Номер группы', max_length=50)
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='groups',
        verbose_name='Направление',
    )
    branch = models.CharField('Филиал', max_length=100, blank=True)
    start_date = models.DateField('Дата начала', null=True, blank=True)
    end_date = models.DateField('Дата окончания', null=True, blank=True, db_index=True)
    students_count = models.PositiveSmallIntegerField('Обучающихся', default=0)
    expected_interns = models.PositiveSmallIntegerField(
        'Прогноз перехода в стажировку', default=0,
    )
    actual_interns = models.PositiveSmallIntegerField(
        'Фактически пришло', default=0,
    )

    class Meta:
        verbose_name = 'Учебная группа'
        verbose_name_plural = 'Учебные группы'
        ordering = ['end_date']

    def __str__(self) -> str:
        return f'{self.number} ({self.specialization})'
