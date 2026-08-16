from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Attendance(TimeStampedModel):
    """Отметка табеля: был ли человек на месте в конкретный день.

    Табель ведётся по группам — как в ведомостях GeeksPro.
    """

    class Status(models.TextChoices):
        PRESENT = 'present', 'Был'
        ABSENT = 'absent', 'Не был'
        LATE = 'late', 'Опоздал'
        EXCUSED = 'excused', 'Уважительная'

    # Порядок переключения по клику в табеле
    CYCLE = [Status.PRESENT, Status.ABSENT, Status.LATE, Status.EXCUSED]

    group = models.ForeignKey(
        'flows.Group', on_delete=models.CASCADE, related_name='attendance',
        verbose_name='Группа',
    )
    intern = models.ForeignKey(
        'interns.Intern', on_delete=models.CASCADE, related_name='attendance',
        verbose_name='Человек',
    )
    date = models.DateField('Дата', db_index=True)
    status = models.CharField(
        'Отметка', max_length=10, choices=Status.choices,
        default=Status.PRESENT,
    )
    comment = models.CharField('Комментарий', max_length=255, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Отметил', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Отметка табеля'
        verbose_name_plural = 'Табель'
        ordering = ['date']
        unique_together = [('group', 'intern', 'date')]
        indexes = [models.Index(fields=['group', 'date'])]

    def __str__(self) -> str:
        return f'{self.intern} — {self.date:%d.%m.%Y}: {self.get_status_display()}'

    @property
    def is_attended(self) -> bool:
        """Считается ли отметка присутствием (для процента посещаемости)."""
        return self.status in (self.Status.PRESENT, self.Status.LATE)
