import secrets

from django.conf import settings
from django.db import models

from apps.common.models import ArchivableModel, TimeStampedModel
from apps.projects.models import Project


def generate_brief_token() -> str:
    return secrets.token_urlsafe(16)


class DocumentType(models.Model):
    """Тип документа (ТЗ §17). Справочник, пополняется через админку.

    ``code`` — стабильный ключ для программных проверок (delivery, warnings).
    ``required_for_delivery`` — документ обязателен перед сдачей проекта.
    """

    code = models.SlugField('Код', max_length=50, unique=True)
    name = models.CharField('Название', max_length=100)
    required_for_delivery = models.BooleanField(
        'Обязателен для сдачи', default=False,
    )

    class Meta:
        verbose_name = 'Тип документа'
        verbose_name_plural = 'Типы документов'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


# Коды базовых типов — используются в проверках delivery
BRIEF = 'brief'
CONTRACT = 'contract'
REQUIREMENTS = 'requirements'
ACCEPTANCE_ACT = 'acceptance_act'

DEFAULT_TYPES = [
    # (code, name, required_for_delivery)
    (BRIEF, 'Бриф заказчика', True),
    (CONTRACT, 'Договор', True),
    (REQUIREMENTS, 'ТЗ', True),
    (ACCEPTANCE_ACT, 'Акт приёма-передачи', True),
]


class DocumentStatus(models.TextChoices):
    DRAFT = 'draft', 'Черновик'
    AWAITING_SIGNATURE = 'awaiting', 'Ожидает подписи'
    SIGNED = 'signed', 'Подписан'
    EXPIRED = 'expired', 'Истёк'
    CANCELLED = 'cancelled', 'Отменён'


class Document(TimeStampedModel, ArchivableModel):
    """Документ проекта (ТЗ §17)."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='documents',
        verbose_name='Проект',
    )
    doc_type = models.ForeignKey(
        DocumentType, on_delete=models.PROTECT, related_name='documents',
        verbose_name='Тип',
    )
    number = models.CharField('Номер', max_length=100, blank=True)
    file = models.FileField('Файл', upload_to='documents/%Y/%m/', blank=True)
    document_date = models.DateField('Дата документа', null=True, blank=True)
    status = models.CharField(
        'Статус', max_length=20,
        choices=DocumentStatus.choices, default=DocumentStatus.DRAFT,
        db_index=True,
    )
    is_signed = models.BooleanField('Подписан', default=False)
    signed_date = models.DateField('Дата подписания', null=True, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'
        ordering = ['-created_at']

    def __str__(self) -> str:
        label = f'{self.doc_type} {self.number}'.strip()
        return f'{label} — {self.project.code}'


class DocumentTemplate(TimeStampedModel):
    """Шаблон документа — не привязан к проекту.

    ПМ берёт файл отсюда за основу, когда готовит настоящий документ по
    проекту (Document). Один тип документа может иметь несколько
    шаблонов — например, разные варианты договора.
    """

    doc_type = models.ForeignKey(
        DocumentType, on_delete=models.CASCADE, related_name='templates',
        verbose_name='Тип',
    )
    name = models.CharField('Название', max_length=150, blank=True)
    file = models.FileField('Файл шаблона', upload_to='document_templates/%Y/%m/')
    comment = models.TextField('Комментарий', blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Загрузил', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Шаблон документа'
        verbose_name_plural = 'Шаблоны документов'
        ordering = ['doc_type__name', '-created_at']

    def __str__(self) -> str:
        return self.name or str(self.doc_type)


class ProjectBriefLink(TimeStampedModel):
    """Ссылка на бриф — под конкретный проект, без входа в систему.

    ПМ выпускает ссылку и отправляет заказчику сам (WhatsApp/Telegram/
    email — вручную, система ничего не рассылает). Заполнение обновляет
    один и тот же ``ProjectBrief`` проекта — повторная отправка по новой
    ссылке просто правит те же ответы, а не плодит дубли.
    """

    token = models.CharField(
        'Токен', max_length=64, unique=True, default=generate_brief_token,
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name='brief_links',
        verbose_name='Проект',
    )
    is_active = models.BooleanField('Активна', default=True)
    expires_at = models.DateTimeField('Действует до', null=True, blank=True)
    submissions = models.PositiveIntegerField('Заполнений', default=0)
    used_at = models.DateTimeField('Последнее заполнение', null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        related_name='+', verbose_name='Создал', null=True, blank=True,
    )

    class Meta:
        verbose_name = 'Ссылка на бриф'
        verbose_name_plural = 'Ссылки на бриф'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Бриф «{self.project}» /{self.token}/'

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse('project_brief_apply', args=[self.token])

    def deactivate(self) -> None:
        self.is_active = False
        self.save(update_fields=['is_active', 'updated_at'])

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone

        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_open(self) -> bool:
        return self.is_active and not self.is_expired


class ProjectBrief(TimeStampedModel):
    """Ответы заказчика по брифу — одна карточка на проект.

    Контакты (компания/ФИО/телефон/email) сюда не входят — они пишутся
    в карточку клиента проекта (Client), не дублируются здесь.
    """

    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name='brief',
        verbose_name='Проект',
    )
    about_business = models.TextField('О бизнесе', blank=True)
    goal = models.TextField('Цель проекта', blank=True)
    target_audience = models.TextField('Целевая аудитория', blank=True)
    required_features = models.TextField('Обязательный функционал', blank=True)
    references = models.TextField('Референсы', blank=True)
    deadline_wish = models.CharField('Желаемый срок', max_length=255, blank=True)
    existing_site_url = models.CharField(
        'Действующий сайт/приложение', max_length=500, blank=True,
    )
    domain = models.CharField('Домен', max_length=255, blank=True)
    integrations = models.TextField('Нужные интеграции', blank=True)
    languages = models.CharField('Язык(и)', max_length=255, blank=True)
    content_owner = models.CharField(
        'Кто наполняет контентом', max_length=255, blank=True,
    )
    social_links = models.TextField('Соцсети компании', blank=True)

    competitors = models.TextField('Конкуренты', blank=True)
    brand_materials = models.CharField(
        'Бренд-бук/логотип', max_length=500, blank=True,
    )
    decision_maker = models.CharField(
        'Кто принимает решение', max_length=255, blank=True,
    )
    requirements_file = models.FileField(
        'Готовое ТЗ/документация', upload_to='project_briefs/%Y/%m/', blank=True,
    )
    preferred_contact = models.CharField(
        'Удобный способ связи', max_length=255, blank=True,
    )
    additional_notes = models.TextField('Доп. пожелания', blank=True)

    submitted_at = models.DateTimeField('Отправлен', null=True, blank=True)

    # Поля брифа в порядке отображения — файл и служебные поля сюда не
    # входят, они показываются отдельно.
    DISPLAY_FIELDS = [
        'about_business', 'goal', 'target_audience', 'required_features',
        'references', 'deadline_wish', 'existing_site_url', 'domain',
        'integrations', 'languages', 'content_owner', 'social_links',
        'competitors', 'brand_materials', 'decision_maker',
        'preferred_contact', 'additional_notes',
    ]

    class Meta:
        verbose_name = 'Бриф проекта'
        verbose_name_plural = 'Брифы проектов'

    def __str__(self) -> str:
        return f'Бриф «{self.project}»'

    @property
    def display_rows(self):
        """Список (подпись, значение) для read-only показа ПМ."""
        return [
            (self._meta.get_field(name).verbose_name, getattr(self, name))
            for name in self.DISPLAY_FIELDS
        ]
