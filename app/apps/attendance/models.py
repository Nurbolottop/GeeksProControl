import datetime

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class MeetingKind(models.TextChoices):
    """Виды регулярных собраний GeeksPro."""

    PM_INTERNS = 'pm_interns', 'PM со стажёрами'
    LEAD_INTERNS = 'lead_interns', 'Тимлид со стажёрами'
    INTERNAL = 'internal', 'Внутреннее (PM и тимлиды)'
    OTHER = 'other', 'Другое'


WEEKDAYS = [
    (0, 'Пн'), (1, 'Вт'), (2, 'Ср'), (3, 'Чт'),
    (4, 'Пт'), (5, 'Сб'), (6, 'Вс'),
]


class GroupMeeting(TimeStampedModel):
    """Собрание группы: конкретная дата, по которой ведётся табель."""

    class Status(models.TextChoices):
        PLANNED = 'planned', 'Запланировано'
        HELD = 'held', 'Проведено'
        MISSED = 'missed', 'Не проведено'

    group = models.ForeignKey(
        'flows.Group', on_delete=models.CASCADE, related_name='meetings',
        verbose_name='Группа',
    )
    kind = models.CharField(
        'Вид', max_length=20,
        choices=MeetingKind.choices, default=MeetingKind.PM_INTERNS,
    )
    date = models.DateField('Дата', db_index=True)
    host = models.ForeignKey(
        'interns.Intern', on_delete=models.SET_NULL, related_name='hosted_meetings',
        verbose_name='Провёл', null=True, blank=True,
    )
    status = models.CharField(
        'Статус', max_length=10,
        choices=Status.choices, default=Status.PLANNED, db_index=True,
    )
    topic = models.CharField('Тема', max_length=255, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Собрание группы'
        verbose_name_plural = 'Собрания групп'
        ordering = ['date']
        unique_together = [('group', 'kind', 'date')]
        indexes = [models.Index(fields=['group', 'date'])]

    def __str__(self) -> str:
        return f'{self.get_kind_display()} {self.date:%d.%m.%Y}'

    @property
    def short_kind(self) -> str:
        return {
            MeetingKind.PM_INTERNS: 'PM',
            MeetingKind.LEAD_INTERNS: 'ТЛ',
            MeetingKind.INTERNAL: 'Вн',
        }.get(self.kind, '—')

    @property
    def attendance_rate(self):
        marks = list(self.attendance.all())
        if not marks:
            return None
        attended = sum(1 for mark in marks if mark.is_attended)
        return round(attended / len(marks) * 100)


class Attendance(TimeStampedModel):
    """Отметка посещения конкретного собрания."""

    class Status(models.TextChoices):
        PRESENT = 'present', 'Был'
        ABSENT = 'absent', 'Не был'
        LATE = 'late', 'Опоздал'
        EXCUSED = 'excused', 'Уважительная'

    # Порядок переключения по клику в табеле
    CYCLE = [Status.PRESENT, Status.ABSENT, Status.LATE, Status.EXCUSED]

    meeting = models.ForeignKey(
        GroupMeeting, on_delete=models.CASCADE, related_name='attendance',
        verbose_name='Собрание',
    )
    intern = models.ForeignKey(
        'interns.Intern', on_delete=models.CASCADE, related_name='attendance',
        verbose_name='Человек',
    )
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
        verbose_name = 'Отметка посещения'
        verbose_name_plural = 'Табель посещаемости'
        unique_together = [('meeting', 'intern')]

    def __str__(self) -> str:
        return f'{self.intern} — {self.meeting}: {self.get_status_display()}'

    @property
    def is_attended(self) -> bool:
        return self.status in (self.Status.PRESENT, self.Status.LATE)
