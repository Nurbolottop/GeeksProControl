"""Резерв кадров: база проверенных стажёров и выпускников, которых
GeeksPro рекомендует компаниям на работу.

Карточка кандидата состоит из двух половин: публичную заполняет сам
кандидат по персональной ссылке (`ReserveInvite`), внутреннюю —
сотрудники студии (учебная информация, оценки, решение, статус).
Всё, что уже есть в системе — человек, его проекты, роли, компании —
берётся связями, а не копируется: `intern` → `interns.Intern`,
рекомендация → `clients.Client`.
"""
import secrets

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from apps.common.models import ArchivableModel, TimeStampedModel
from apps.training.models import Specialization, TrainingGroup


class CandidateStatus(models.TextChoices):
    """Путь кандидата от анкеты до трудоустройства."""

    NEW = 'new', 'Новый'
    REVIEW = 'review', 'На проверке'
    RESERVE = 'reserve', 'В резерве'
    PROPOSED = 'proposed', 'Предложен компании'
    INTERVIEW = 'interview', 'Собеседование'
    OFFER = 'offer', 'Получил оффер'
    EMPLOYED = 'employed', 'Трудоустроен'
    INACTIVE = 'inactive', 'Неактивен'
    DECLINED = 'declined', 'Отказался'
    NOT_READY = 'not_ready', 'Пока не готов к работе'


# Как красить статус в списке и в карточке
STATUS_TONE = {
    CandidateStatus.NEW: 'gray',
    CandidateStatus.REVIEW: 'yellow',
    CandidateStatus.RESERVE: 'green',
    CandidateStatus.PROPOSED: 'blue',
    CandidateStatus.INTERVIEW: 'blue',
    CandidateStatus.OFFER: 'green',
    CandidateStatus.EMPLOYED: 'green',
    CandidateStatus.INACTIVE: 'gray',
    CandidateStatus.DECLINED: 'red',
    CandidateStatus.NOT_READY: 'orange',
}


class CandidateLevel(models.TextChoices):
    """Уровень по внутренней оценке GeeksPro."""

    INTERN = 'intern', 'Intern'
    JUNIOR = 'junior', 'Junior'
    JUNIOR_PLUS = 'junior_plus', 'Junior+'
    MIDDLE = 'middle', 'Middle'
    MIDDLE_PLUS = 'middle_plus', 'Middle+'


class WorkFormat(models.TextChoices):
    OFFICE = 'office', 'Офис'
    REMOTE = 'remote', 'Удалённо'
    HYBRID = 'hybrid', 'Гибрид'
    ANY = 'any', 'Любой формат'


class Employment(models.TextChoices):
    FULL = 'full', 'Полная занятость'
    PARTIAL = 'partial', 'Частичная занятость'
    ANY = 'any', 'Любая занятость'


class Decision(models.TextChoices):
    """Внутреннее решение студии по кандидату."""

    RECOMMEND = 'recommend', 'Рекомендуем'
    WITH_NOTES = 'with_notes', 'Рекомендуем с оговорками'
    NOT_YET = 'not_yet', 'Пока не рекомендуем'


def generate_token() -> str:
    return secrets.token_urlsafe(16)


class ReserveCandidate(TimeStampedModel, ArchivableModel):
    """Кандидат в резерве кадров."""

    # Оценка: поле → подпись. Шкала 1–10, средний балл считается по
    # заполненным критериям (services.recalculate_rating).
    EVALUATION_CRITERIA = [
        ('score_hard_skills', 'Hard skills'),
        ('score_quality', 'Качество работы'),
        ('score_independence', 'Самостоятельность'),
        ('score_responsibility', 'Ответственность'),
        ('score_deadlines', 'Соблюдение дедлайнов'),
        ('score_communication', 'Коммуникация'),
        ('score_teamwork', 'Работа в команде'),
        ('score_learning', 'Обучаемость'),
    ]

    # --- связь с уже существующими данными платформы ---
    intern = models.OneToOneField(
        'interns.Intern', on_delete=models.SET_NULL, related_name='reserve_card',
        verbose_name='Карточка стажёра', null=True, blank=True,
        help_text='Если кандидат — наш стажёр: проекты и роли берутся оттуда.',
    )

    # --- личные данные (заполняет кандидат) ---
    full_name = models.CharField('ФИО', max_length=255)
    birth_date = models.DateField('Дата рождения', null=True, blank=True)
    city = models.CharField('Город проживания', max_length=100, blank=True, db_index=True)
    phone = models.CharField('Телефон', max_length=32, blank=True)
    telegram = models.CharField('Telegram', max_length=100, blank=True)
    email = models.EmailField('Email', blank=True)
    photo = models.FileField('Фото', upload_to='reserve/photo/%Y/%m/', blank=True)

    # --- профессиональные данные ---
    specialization = models.ForeignKey(
        Specialization, on_delete=models.PROTECT, related_name='reserve_pool',
        verbose_name='Направление', null=True, blank=True, db_index=True,
    )
    direction_other = models.CharField(
        'Направление (другое)', max_length=100, blank=True,
        help_text='Если направления нет в списке.',
    )
    desired_position = models.CharField('Желаемая должность', max_length=255, blank=True)
    expected_level = models.CharField(
        'Предполагаемый уровень (со слов кандидата)', max_length=20,
        choices=CandidateLevel.choices, blank=True,
    )
    skills = models.TextField(
        'Навыки и технологии', blank=True,
        help_text='Через запятую: Python, Django, PostgreSQL…',
    )
    work_experience = models.TextField('Опыт работы', blank=True)
    internship_experience = models.TextField('Опыт стажировки', blank=True)
    education = models.TextField('Образование', blank=True)
    courses = models.TextField('Пройденные курсы', blank=True)
    english_level = models.CharField('Уровень английского', max_length=50, blank=True)
    other_languages = models.CharField('Другие языки', max_length=255, blank=True)
    about = models.TextField('О себе', blank=True)

    # --- ссылки и документы ---
    resume_file = models.FileField('Резюме (файл)', upload_to='reserve/resume/%Y/%m/', blank=True)
    resume_url = models.URLField('Резюме (ссылка)', blank=True)
    github_url = models.URLField('GitHub', blank=True)
    linkedin_url = models.URLField('LinkedIn', blank=True)
    portfolio_url = models.URLField('Портфолио', blank=True)
    behance_url = models.URLField('Behance', blank=True)
    website_url = models.URLField('Личный сайт', blank=True)
    project_links = models.TextField('Ссылки на проекты', blank=True)

    # --- поиск работы ---
    is_looking_for_job = models.BooleanField('Ищет работу сейчас', default=True, db_index=True)
    work_format = models.CharField(
        'Формат работы', max_length=10, choices=WorkFormat.choices, blank=True,
    )
    employment_type = models.CharField(
        'Тип занятости', max_length=10, choices=Employment.choices, blank=True,
    )
    ready_for_internship = models.BooleanField('Готов(а) к стажировке', default=False)
    ready_to_relocate = models.BooleanField('Готов(а) к переезду', default=False)
    available_from = models.DateField('Когда готов(а) приступить', null=True, blank=True)
    desired_salary = models.CharField('Желаемая зарплата', max_length=100, blank=True)
    target_positions = models.TextField('Какие вакансии рассматривает', blank=True)

    # --- согласие на передачу данных работодателям ---
    consent_given = models.BooleanField('Согласие на обработку и передачу данных', default=False)
    consent_at = models.DateTimeField('Дата согласия', null=True, blank=True)

    # --- внутреннее: учебная информация ---
    training_group = models.ForeignKey(
        TrainingGroup, on_delete=models.SET_NULL, related_name='reserve_pool',
        verbose_name='Учебная группа', null=True, blank=True,
    )
    study_specialization = models.ForeignKey(
        Specialization, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Направление обучения', null=True, blank=True,
    )
    teacher = models.CharField('Преподаватель', max_length=255, blank=True)
    curator = models.CharField('Куратор', max_length=255, blank=True)
    study_start = models.DateField('Начало обучения', null=True, blank=True)
    study_end = models.DateField('Окончание обучения', null=True, blank=True)

    # --- внутреннее: оценка 1–10 ---
    score_hard_skills = models.PositiveSmallIntegerField(
        'Hard skills', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_quality = models.PositiveSmallIntegerField(
        'Качество работы', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_independence = models.PositiveSmallIntegerField(
        'Самостоятельность', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_responsibility = models.PositiveSmallIntegerField(
        'Ответственность', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_deadlines = models.PositiveSmallIntegerField(
        'Соблюдение дедлайнов', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_communication = models.PositiveSmallIntegerField(
        'Коммуникация', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_teamwork = models.PositiveSmallIntegerField(
        'Работа в команде', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    score_learning = models.PositiveSmallIntegerField(
        'Обучаемость', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    rating = models.DecimalField(
        'Общий рейтинг', max_digits=4, decimal_places=2,
        null=True, blank=True, db_index=True,
        help_text='Считается автоматически по выставленным оценкам.',
    )

    # --- внутреннее: выводы ---
    strengths = models.TextField('Сильные стороны', blank=True)
    improvements = models.TextField('Что необходимо улучшить', blank=True)
    comment_teacher = models.TextField('Комментарий преподавателя', blank=True)
    comment_pm = models.TextField('Комментарий PM', blank=True)
    comment_lead = models.TextField('Комментарий Team Lead', blank=True)
    comment_curator = models.TextField('Комментарий куратора', blank=True)
    recommended_position = models.CharField(
        'Рекомендуемая должность', max_length=255, blank=True,
    )
    geekspro_level = models.CharField(
        'Уровень по оценке GeeksPro', max_length=20,
        choices=CandidateLevel.choices, blank=True, db_index=True,
    )
    decision = models.CharField(
        'Решение', max_length=20, choices=Decision.choices, blank=True,
    )
    decision_comment = models.TextField('Причина / комментарий', blank=True)

    # --- статус и служебное ---
    status = models.CharField(
        'Статус', max_length=20, choices=CandidateStatus.choices,
        default=CandidateStatus.NEW, db_index=True,
    )
    status_changed_at = models.DateTimeField('Статус изменён', null=True, blank=True)
    submitted_at = models.DateTimeField('Анкета заполнена', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Добавил', null=True, blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Последнее изменение', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Кандидат резерва'
        verbose_name_plural = 'Резерв кадров'
        ordering = ['-rating', 'full_name']

    def __str__(self) -> str:
        return self.full_name

    def get_absolute_url(self) -> str:
        return reverse('reserve:detail', args=[self.pk])

    @property
    def status_tone(self) -> str:
        return STATUS_TONE.get(self.status, 'gray')

    @property
    def direction(self) -> str:
        """Направление: из справочника или произвольное «другое»."""
        return str(self.specialization) if self.specialization_id else (self.direction_other or '—')

    @property
    def skills_list(self) -> list[str]:
        return [s.strip() for s in self.skills.replace('\n', ',').split(',') if s.strip()]

    @property
    def project_links_list(self) -> list[str]:
        return [s.strip() for s in self.project_links.split() if s.strip()]

    @property
    def scores(self) -> list[tuple[str, int | None]]:
        return [(label, getattr(self, field)) for field, label in self.EVALUATION_CRITERIA]

    @property
    def is_evaluated(self) -> bool:
        return self.rating is not None

    @property
    def project_memberships(self):
        """Проекты GeeksPro — из существующих команд, без дублирования."""
        if not self.intern_id:
            return []
        return list(
            self.intern.team_memberships
            .select_related('project')
            .prefetch_related('project__team_members__intern')
            .order_by('-joined_at'),
        )

    @property
    def projects_count(self) -> int:
        return len(self.project_memberships)

    @property
    def recommendations_count(self) -> int:
        return self.recommendations.count()

    @property
    def readiness(self) -> str:
        if not self.is_looking_for_job:
            return 'Не ищет работу'
        if self.available_from:
            return f'С {self.available_from:%d.%m.%Y}'
        return 'Готов(а) сейчас'


class ReserveInvite(TimeStampedModel):
    """Ссылка на анкету кандидата. Бывает двух видов.

    Общая (`candidate` пустой) — просто вход в пустую анкету: создали,
    раздали, при необходимости отключили. Заполнить её может сколько
    угодно людей, каждое заполнение заводит свою карточку.

    На редактирование (`candidate` заполнен) — открывает анкету
    конкретного человека уже с его данными, отправка обновляет ту же
    карточку. Ни списка кандидатов, ни внутренних оценок по ссылке
    по-прежнему не видно.
    """

    token = models.CharField('Токен', max_length=64, unique=True, default=generate_token)
    candidate = models.ForeignKey(
        ReserveCandidate, on_delete=models.CASCADE, related_name='edit_links',
        verbose_name='Кандидат', null=True, blank=True,
        help_text='Пусто — общая ссылка на анкету; иначе ссылка на правку карточки.',
    )
    recipient = models.CharField(
        'Заметка', max_length=255, blank=True,
        help_text='Для кого создана ссылка — чтобы не путать несколько ссылок.',
    )
    is_active = models.BooleanField('Активна', default=True)
    expires_at = models.DateTimeField('Действует до', null=True, blank=True)
    submissions = models.PositiveIntegerField('Заполнений', default=0)
    used_at = models.DateTimeField('Последнее заполнение', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Создал', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Приглашение в резерв'
        verbose_name_plural = 'Приглашения в резерв'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Анкета резерва /{self.token}/'

    @property
    def is_edit_link(self) -> bool:
        return self.candidate_id is not None

    def get_absolute_url(self) -> str:
        return reverse('reserve_apply', args=[self.token])

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_open(self) -> bool:
        return self.is_active and not self.is_expired

    def deactivate(self) -> None:
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])


class RecommendationStatus(models.TextChoices):
    SENT = 'sent', 'Отправлено'
    REVIEW = 'review', 'Рассматривается'
    INTERVIEW = 'interview', 'Приглашён на собеседование'
    COMPANY_REJECT = 'company_reject', 'Отказ компании'
    CANDIDATE_REJECT = 'candidate_reject', 'Отказ кандидата'
    OFFER = 'offer', 'Оффер'
    HIRED = 'hired', 'Принят на работу'


REC_STATUS_TONE = {
    RecommendationStatus.SENT: 'gray',
    RecommendationStatus.REVIEW: 'yellow',
    RecommendationStatus.INTERVIEW: 'blue',
    RecommendationStatus.COMPANY_REJECT: 'red',
    RecommendationStatus.CANDIDATE_REJECT: 'red',
    RecommendationStatus.OFFER: 'green',
    RecommendationStatus.HIRED: 'green',
}


class ReserveRecommendation(TimeStampedModel):
    """Кандидат рекомендован компании. История не удаляется."""

    candidate = models.ForeignKey(
        ReserveCandidate, on_delete=models.CASCADE, related_name='recommendations',
        verbose_name='Кандидат',
    )
    company = models.ForeignKey(
        'clients.Client', on_delete=models.PROTECT, related_name='reserve_recommendations',
        verbose_name='Компания', null=True, blank=True,
    )
    company_name = models.CharField(
        'Компания (вне базы)', max_length=255, blank=True,
        help_text='Заполняется, если компании ещё нет в списке заказчиков.',
    )
    vacancy = models.CharField('Вакансия', max_length=255, blank=True)
    sent_on = models.DateField('Дата рекомендации')
    status = models.CharField(
        'Статус', max_length=20, choices=RecommendationStatus.choices,
        default=RecommendationStatus.SENT, db_index=True,
    )
    comment = models.TextField('Комментарий', blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Кто рекомендовал', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Рекомендация компании'
        verbose_name_plural = 'Рекомендации компаниям'
        ordering = ['-sent_on', '-created_at']

    def __str__(self) -> str:
        return f'{self.candidate} → {self.company_title}'

    @property
    def company_title(self) -> str:
        return str(self.company) if self.company_id else (self.company_name or '—')

    @property
    def status_tone(self) -> str:
        return REC_STATUS_TONE.get(self.status, 'gray')


class EventKind(models.TextChoices):
    CREATED = 'created', 'Кандидат добавлен'
    INVITED = 'invited', 'Отправлена ссылка на анкету'
    SUBMITTED = 'submitted', 'Анкета заполнена'
    UPDATED = 'updated', 'Данные изменены'
    STATUS = 'status', 'Смена статуса'
    EVALUATED = 'evaluated', 'Внутренняя оценка'
    RECOMMENDED = 'recommended', 'Рекомендация компании'
    REC_STATUS = 'rec_status', 'Результат по рекомендации'


class ReserveEvent(TimeStampedModel):
    """История кандидата — пишется автоматически и не удаляется."""

    candidate = models.ForeignKey(
        ReserveCandidate, on_delete=models.CASCADE, related_name='events',
        verbose_name='Кандидат',
    )
    kind = models.CharField('Событие', max_length=20, choices=EventKind.choices)
    title = models.CharField('Что произошло', max_length=255)
    detail = models.TextField('Подробности', blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='+',
        verbose_name='Пользователь', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Событие кандидата'
        verbose_name_plural = 'История кандидатов'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.get_kind_display()} — {self.candidate}'
