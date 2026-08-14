from django.db import models

from apps.common.models import TimeStampedModel


class NotificationLevel(models.TextChoices):
    CRITICAL = 'critical', 'Critical'
    WARNING = 'warning', 'Warning'
    INFO = 'info', 'Information'
    SUCCESS = 'success', 'Success'


class Notification(TimeStampedModel):
    """Внутреннее уведомление (ТЗ §23).

    ``dedup_key`` защищает от дублей при ежедневных автоматических
    проверках: пока уведомление не закрыто, повторная проверка
    не создаёт такое же.
    """

    title = models.CharField('Название', max_length=255)
    description = models.TextField('Описание', blank=True)
    level = models.CharField(
        'Тип', max_length=10,
        choices=NotificationLevel.choices, default=NotificationLevel.INFO,
        db_index=True,
    )
    url = models.CharField('Ссылка на объект', max_length=255, blank=True)
    dedup_key = models.CharField(
        'Ключ дедупликации', max_length=255, blank=True, db_index=True,
    )
    is_read = models.BooleanField('Просмотрено', default=False, db_index=True)
    is_closed = models.BooleanField('Закрыто', default=False, db_index=True)

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.title
