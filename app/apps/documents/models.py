from django.conf import settings
from django.db import models

from apps.common.models import ArchivableModel, TimeStampedModel
from apps.projects.models import Project


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
