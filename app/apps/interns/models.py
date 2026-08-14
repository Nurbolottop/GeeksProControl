from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.common.models import ArchivableModel, TimeStampedModel
from apps.training.models import Specialization, TrainingGroup


class InternStatus(models.TextChoices):
    """Статусы стажёра (ТЗ §12)."""

    WAITING = 'waiting', 'Ожидает стажировки'
    READY = 'ready', 'Готов к распределению'
    INTERNSHIP = 'internship', 'На стажировке'
    ACTIVE = 'active', 'Активный'
    PAUSED = 'paused', 'Приостановлен'
    EMPLOYABLE = 'employable', 'Готов к трудоустройству'
    EMPLOYED = 'employed', 'Трудоустроен'
    DROPPED = 'dropped', 'Выбыл'


# Статусы, при которых стажёр считается работающим в GeeksPro
WORKING_STATUSES = (InternStatus.INTERNSHIP, InternStatus.ACTIVE)


class Intern(TimeStampedModel, ArchivableModel):
    """Карточка стажёра (ТЗ §12)."""

    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    email = models.EmailField('Email', blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    branch = models.CharField('Филиал', max_length=100, blank=True)
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='interns',
        verbose_name='Направление', null=True, blank=True, db_index=True,
    )
    training_group = models.ForeignKey(
        TrainingGroup, on_delete=models.SET_NULL, related_name='interns',
        verbose_name='Учебная группа', null=True, blank=True,
    )
    education_end_date = models.DateField(
        'Дата окончания обучения', null=True, blank=True,
    )
    internship_start_date = models.DateField(
        'Дата начала стажировки', null=True, blank=True,
    )
    status = models.CharField(
        'Статус', max_length=20,
        choices=InternStatus.choices, default=InternStatus.WAITING, db_index=True,
    )
    team_lead = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='mentored_interns', verbose_name='Текущий Team Lead',
        null=True, blank=True,
    )
    rating = models.DecimalField(
        'Рейтинг', max_digits=3, decimal_places=2, null=True, blank=True,
    )
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Стажёр'
        verbose_name_plural = 'Стажёры'
        ordering = ['full_name']

    def __str__(self) -> str:
        return self.full_name

    def get_absolute_url(self) -> str:
        return reverse('interns:detail', args=[self.pk])

    @property
    def active_memberships(self):
        return [
            m for m in self.team_memberships.all() if m.status == 'active'
        ]


class InternEvaluation(TimeStampedModel):
    """Оценка стажёра по 7 критериям, шкала 1–5 (ТЗ §12.1)."""

    CRITERIA = [
        ('hard_skills', 'Hard skills'),
        ('quality', 'Качество работы'),
        ('speed', 'Скорость'),
        ('responsibility', 'Ответственность'),
        ('communication', 'Коммуникация'),
        ('teamwork', 'Teamwork'),
        ('independence', 'Самостоятельность'),
    ]
    SCORE_CHOICES = [(i, str(i)) for i in range(1, 6)]

    intern = models.ForeignKey(
        Intern, on_delete=models.CASCADE, related_name='evaluations',
        verbose_name='Стажёр',
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, related_name='+',
        verbose_name='Проект', null=True, blank=True,
    )
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Оценил', null=True,
    )
    hard_skills = models.PositiveSmallIntegerField('Hard skills', choices=SCORE_CHOICES)
    quality = models.PositiveSmallIntegerField('Качество работы', choices=SCORE_CHOICES)
    speed = models.PositiveSmallIntegerField('Скорость', choices=SCORE_CHOICES)
    responsibility = models.PositiveSmallIntegerField('Ответственность', choices=SCORE_CHOICES)
    communication = models.PositiveSmallIntegerField('Коммуникация', choices=SCORE_CHOICES)
    teamwork = models.PositiveSmallIntegerField('Teamwork', choices=SCORE_CHOICES)
    independence = models.PositiveSmallIntegerField('Самостоятельность', choices=SCORE_CHOICES)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Оценка стажёра'
        verbose_name_plural = 'Оценки стажёров'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Оценка {self.intern} от {self.created_at:%d.%m.%Y}'

    @property
    def average(self) -> float:
        scores = [getattr(self, key) for key, _ in self.CRITERIA]
        return round(sum(scores) / len(scores), 2)
