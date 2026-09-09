from django.conf import settings
from django.core.validators import MinValueValidator
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


class Branch(models.TextChoices):
    """Филиал — сейчас у студии их два."""

    BISHKEK = 'Бишкек', 'Бишкек'
    OSH = 'Ош', 'Ош'


class Intern(TimeStampedModel, ArchivableModel):
    """Карточка стажёра (ТЗ §12)."""

    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    email = models.EmailField('Email', blank=True)
    telegram = models.CharField('Telegram', max_length=100, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    branch = models.CharField(
        'Филиал', max_length=20, choices=Branch.choices, blank=True,
    )
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='interns',
        verbose_name='Направление', null=True, blank=True, db_index=True,
    )
    training_group = models.ForeignKey(
        TrainingGroup, on_delete=models.SET_NULL, related_name='interns',
        verbose_name='Учебная группа', null=True, blank=True,
    )
    flow = models.ForeignKey(
        'flows.Flow', on_delete=models.SET_NULL, related_name='interns',
        verbose_name='Поток', null=True, blank=True, db_index=True,
    )
    education_end_date = models.DateField(
        'Дата окончания обучения', null=True, blank=True,
    )
    internship_start_date = models.DateField(
        'Дата начала стажировки', null=True, blank=True,
    )
    internship_attempt = models.PositiveSmallIntegerField(
        'Какая по счёту стажировка', default=1,
        validators=[MinValueValidator(1)],
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
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='intern_profile', verbose_name='Учётная запись',
        null=True, blank=True,
    )
    in_resume_bank = models.BooleanField('В банке резюме', default=False)
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


class TalentReserveCandidate(TimeStampedModel, ArchivableModel):
    """Резерв кадров — отдельный пул людей, не привязан к карточке стажёра.

    По факту сюда обычно попадают наши же бывшие стажёры/тимлиды, но
    запись самостоятельная: нет связи с Intern, свой набор полей.
    """

    full_name = models.CharField('ФИО', max_length=255)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    email = models.EmailField('Email', blank=True)
    telegram = models.CharField('Telegram', max_length=100, blank=True)
    city = models.CharField('Город', max_length=100, blank=True)
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='reserve_candidates',
        verbose_name='Направление', null=True, blank=True,
    )
    desired_role = models.CharField('Желаемая роль/позиция', max_length=255, blank=True)
    experience = models.TextField('О себе / опыт', blank=True)
    portfolio_link = models.URLField('Портфолио / резюме — ссылка', blank=True)
    priority = models.PositiveIntegerField(
        'Приоритет', default=0,
        help_text='Чем больше число, тем выше в списке.',
    )
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Кандидат в резерве'
        verbose_name_plural = 'Резерв кадров'
        ordering = ['-priority', '-created_at']

    def __str__(self) -> str:
        return self.full_name


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
