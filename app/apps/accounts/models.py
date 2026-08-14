from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Пользователь системы.

    В первой версии реально работает только Head (руководитель GeeksPro),
    но роли заложены заранее, чтобы добавление PM/TL/стажёров
    не потребовало переделки схемы (ТЗ §2).
    """

    class Role(models.TextChoices):
        HEAD = 'head', 'Руководитель'
        PROJECT_MANAGER = 'pm', 'Project Manager'
        TEAM_LEAD = 'team_lead', 'Team Lead'
        INTERN = 'intern', 'Стажёр'
        ADMINISTRATOR = 'administrator', 'Администратор'

    role = models.CharField(
        'Роль', max_length=20, choices=Role.choices, default=Role.HEAD,
    )
    phone = models.CharField('Телефон', max_length=32, blank=True)

    class Meta(AbstractUser.Meta):
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username
