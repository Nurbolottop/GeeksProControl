"""Приводит состав стажёров проекта «ОБА» к отчёту от 17.08.2026.

ПМ и тимлиды не трогаются — правится только состав разработчиков,
тестировщиков и дизайнеров.

    python manage.py fix_oba_team
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern, InternStatus
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization

PROJECT = 'ОБА'

# Роли, которые командой не правим — они остаются как есть
KEEP_ROLES = {TeamRole.PROJECT_MANAGER, TeamRole.TEAM_LEAD}

# (ФИО, направление, роль, вышел ли из стажировки)
ROSTER = [
    ('Назирбаева Луиза', 'Backend', TeamRole.BACKEND, False),
    ('Осоркулова Амина', 'Backend', TeamRole.BACKEND, False),
    ('Арапова Адалат', 'Backend', TeamRole.BACKEND, False),
    ('Шактыбеков Даулет', 'Backend', TeamRole.BACKEND, False),
    ('Джалалов Фаррух', 'Backend', TeamRole.BACKEND, False),
    ('Закирова Ассоль', 'Backend', TeamRole.BACKEND, False),
    ('Кангельдиев Тимур', 'Frontend', TeamRole.FRONTEND, False),
    ('Жигитекова Раяна', 'Frontend', TeamRole.FRONTEND, False),
    ('Абдыкапар уулу Улукбек', 'Frontend', TeamRole.FRONTEND, False),
    ('Белеков Азамат', 'Frontend', TeamRole.FRONTEND, False),
    ('Нуралиев Ислам', 'Frontend', TeamRole.FRONTEND, False),
    ('Бекбашев Айбек', 'Testing/QA', TeamRole.QA, False),
    ('Абдрахман', 'Backend', TeamRole.OTHER, True),
]

# Как человек записан в базе сейчас → как должен называться по отчёту
RENAMES = {
    'Жигитекова Назик(Райана) второй проект': 'Жигитекова Раяна',
}


class Command(BaseCommand):
    help = 'Синхронизирует стажёров проекта «ОБА» с отчётом от 17.08.2026'

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.get(name=PROJECT)
        group = getattr(project, 'group', None)

        for old_name, new_name in RENAMES.items():
            intern = Intern.objects.filter(full_name=old_name).first()
            if intern:
                intern.full_name = new_name
                intern.save(update_fields=['full_name', 'updated_at'])
                self.stdout.write(f'  ~ переименован: {old_name} → {new_name}')

        keep = set()
        for name, spec_name, role, has_left in ROSTER:
            spec = Specialization.objects.get_or_create(name=spec_name)[0]
            intern, created = Intern.objects.get_or_create(
                full_name=name,
                defaults={
                    'specialization': spec,
                    'status': (
                        InternStatus.DROPPED if has_left else InternStatus.ACTIVE
                    ),
                    'city': project.city or 'Ош',
                },
            )
            if created:
                self.stdout.write(f'  + человек создан: {name}')

            status = (
                TeamMember.Status.LEFT if has_left else TeamMember.Status.ACTIVE
            )
            member = TeamMember.objects.filter(
                project=project, intern=intern,
            ).first()
            if member is None:
                member = TeamMember.objects.create(
                    project=project, group=group, intern=intern,
                    role=role, status=status,
                    comment='покинул стажировку в начале июля' if has_left else '',
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  + в команду: {name} ({member.get_role_display()})',
                ))
            elif member.role not in KEEP_ROLES:
                member.group = group
                member.role = role
                member.status = status
                member.save(update_fields=[
                    'group', 'role', 'status', 'updated_at',
                ])
            keep.add(member.pk)

        # Лишние — все, кроме ПМ, тимлидов и людей из отчёта
        extra = project.team_members.exclude(pk__in=keep).exclude(
            role__in=KEEP_ROLES,
        )
        for member in extra.select_related('intern'):
            self.stdout.write(self.style.WARNING(
                f'  − убран из команды: {member.intern or member.user}',
            ))
        removed = extra.count()
        extra.delete()

        kept_roles = project.team_members.filter(role__in=KEEP_ROLES)
        self.stdout.write(self.style.SUCCESS(
            f'Команда «{PROJECT}»: {project.team_members.count()} человек '
            f'(убрано {removed}, не тронуто {kept_roles.count()} — ПМ и тимлиды).',
        ))
