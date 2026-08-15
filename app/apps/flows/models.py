from django.db import models
from django.urls import reverse

from apps.common.models import TimeStampedModel


class Flow(TimeStampedModel):
    """Поток — набор стажёров, который вместе ведёт свои проекты.

    Главная сущность GeeksPro: под поток набираются проекты и команда,
    поток отрабатывает несколько месяцев и закрывается.
    """

    class Status(models.TextChoices):
        PLANNED = 'planned', 'Набор'
        ACTIVE = 'active', 'Активный'
        FINISHED = 'finished', 'Завершён'

    number = models.PositiveSmallIntegerField('Номер потока', unique=True)
    status = models.CharField(
        'Статус', max_length=10,
        choices=Status.choices, default=Status.ACTIVE, db_index=True,
    )
    start_date = models.DateField('Начало стажировки', null=True, blank=True)
    end_date = models.DateField('Окончание стажировки', null=True, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    class Meta:
        verbose_name = 'Поток'
        verbose_name_plural = 'Потоки'
        ordering = ['-number']

    def __str__(self) -> str:
        return f'Поток {self.number}'

    def get_absolute_url(self) -> str:
        return reverse('flows:detail', args=[self.pk])
