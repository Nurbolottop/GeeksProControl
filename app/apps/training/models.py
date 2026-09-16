from django.db import models
from django.urls import reverse

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


class GroupStatus(models.TextChoices):
    """Где группа академии находится сейчас."""

    RECRUITING = 'recruiting', 'Набор'
    STUDYING = 'studying', 'Учится'
    GRADUATED = 'graduated', 'Выпущена'
    CANCELLED = 'cancelled', 'Не состоялась'


class TrainingGroup(TimeStampedModel):
    """Учебная группа IT-академии (ТЗ §13).

    Из этих групп приходят стажёры, поэтому по каждой держим три числа:
    сколько учится, сколько сказали, что хотят на стажировку, и сколько
    в итоге дошло. На них строится план-график набора по месяцам.
    """

    number = models.CharField('Номер группы', max_length=50)
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='groups',
        verbose_name='Направление',
    )
    branch = models.CharField('Филиал', max_length=100, blank=True)
    start_date = models.DateField('Дата начала', null=True, blank=True)
    end_date = models.DateField('Дата окончания', null=True, blank=True, db_index=True)
    status = models.CharField(
        'Статус', max_length=12, choices=GroupStatus.choices,
        default=GroupStatus.STUDYING, db_index=True,
    )
    students_count = models.PositiveSmallIntegerField('Обучающихся', default=0)
    wants_internship = models.PositiveSmallIntegerField(
        'Хотят на стажировку', default=0,
        help_text='Сколько студентов сами сказали, что пойдут на стажировку.',
    )
    expected_interns = models.PositiveSmallIntegerField(
        'Прогноз перехода в стажировку', default=0,
        help_text='Наша оценка: сколько реально дойдёт.',
    )
    actual_interns = models.PositiveSmallIntegerField(
        'Фактически пришло', default=0,
    )
    teacher = models.CharField('Преподаватель', max_length=255, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Учебная группа'
        verbose_name_plural = 'Учебные группы'
        ordering = ['end_date']

    def __str__(self) -> str:
        return f'{self.number} ({self.specialization})'

    def get_absolute_url(self) -> str:
        return reverse('training:group_list')

    @property
    def is_open(self) -> bool:
        """Группа ещё в работе — её выпуск попадает в план-график."""
        return self.status in (GroupStatus.RECRUITING, GroupStatus.STUDYING)

    @property
    def conversion(self):
        """Доля дошедших до стажировки, когда группа уже выпущена."""
        if self.status != GroupStatus.GRADUATED or not self.students_count:
            return None
        return round(self.actual_interns / self.students_count * 100)
