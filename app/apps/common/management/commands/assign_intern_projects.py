"""Разовое назначение проектов стажёрам, у которых руководитель
подтвердил конкретный проект вручную (те самые «висящие без проекта»
после кампании самозаполнения). Роль в команде берётся из направления
стажёра — та же логика, что и у формы «+ Добавить в проект».

    python manage.py assign_intern_projects
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams.forms import ROLE_BY_SPECIALIZATION
from apps.teams.models import TeamMember, TeamRole

# (intern_pk, project_pk)
ASSIGNMENTS = [
    (855, 108),  # Тиленбаева Нурайым Курстановна -> ЭОЦ
    (851, 103),  # Темирбекова Эльмира Темирбековна -> Биклин
    (860, 107),  # Таалайбекова Нурсулуу Жээнбековна -> Учкун
    (811, 104),  # Ниязалиев Султан Каныбекович -> Олимпийская школа
    (853, 103),  # Нарынбеков Артур Нарынбекович -> Биклин
    (862, 107),  # мелис абдуллаев -> Учкун
    (821, 103),  # Марасулова Айзира -> Биклин
    (847, 98),   # Беренбаева Анара Амановна -> Омур
    (835, 98),   # Алтыбаев Файиздин -> Омур
    (866, 103),  # Абдыгапар у Абдыкалык -> Биклин
]


class Command(BaseCommand):
    help = 'Назначает подтверждённые проекты стажёрам без команды'

    @transaction.atomic
    def handle(self, *args, **options):
        for intern_pk, project_pk in ASSIGNMENTS:
            intern = Intern.objects.get(pk=intern_pk)
            project = Project.objects.get(pk=project_pk)
            spec = intern.specialization
            role = ROLE_BY_SPECIALIZATION.get(
                spec.name if spec else '', TeamRole.OTHER,
            )
            member = TeamMember.objects.create(
                project=project, group=getattr(project, 'group', None),
                intern=intern, role=role, status=TeamMember.Status.ACTIVE,
                joined_at=timezone.localdate(),
            )
            self.stdout.write(self.style.SUCCESS(
                f'  {intern.full_name} → «{project.name}» ({member.get_role_display()})',
            ))
        self.stdout.write(self.style.SUCCESS('Готово.'))
