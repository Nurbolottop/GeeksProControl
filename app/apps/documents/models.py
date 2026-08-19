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
FINAL_ACT = 'final_act'

DEFAULT_TYPES = [
    # (code, name, required_for_delivery)
    (BRIEF, 'Бриф заказчика', True),
    (CONTRACT, 'Договор', True),
    (REQUIREMENTS, 'ТЗ', True),
    ('annex', 'Приложение', False),
    ('extra_agreement', 'Дополнительное соглашение', False),
    ('acceptance_act', 'Акт приёма-передачи', False),
    ('work_act', 'Акт выполненных работ', False),
    (FINAL_ACT, 'Финальный акт', True),
    ('access_transfer', 'Передача доступов', False),
    ('requisites', 'Реквизиты', False),
    ('other', 'Другое', False),
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
