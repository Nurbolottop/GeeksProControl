"""Приводит команду проекта «Омур» к списку из рабочей таблицы.

Состав по таблице (15 человек): PM, три тимлида направлений,
младший тимлид UX/UI, backend, frontend и QA.

    python manage.py fix_omur_team
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern, InternStatus
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization

PROJECT = 'Омур'

# (имя в базе, направление, роль в команде, пометка)
ROSTER = [
    ('Алтынай', 'PM', TeamRole.PROJECT_MANAGER, ''),
    ('Бексултан', 'Backend', TeamRole.TEAM_LEAD, 'тимлид Backend'),
    ('Ислам', 'Frontend', TeamRole.TEAM_LEAD, 'тимлид Frontend'),
    ('Жумабек', 'UX/UI', TeamRole.TEAM_LEAD, 'тимлид UX/UI'),
    ('Макамбаева Айжаз', 'UX/UI', TeamRole.UXUI, 'младший тимлид UX/UI'),
    ('Мамасаков Артур', 'Backend', TeamRole.BACKEND, ''),
    ('Зуев Мирослав', 'Backend', TeamRole.BACKEND, 'младший тимлид Backend'),
    ('Аяна', 'Backend', TeamRole.BACKEND, ''),
    ('Алтыбаев Алинур', 'Backend', TeamRole.BACKEND, ''),
    ('Алтынбекова Дилназ', 'Frontend', TeamRole.FRONTEND, ''),
    ('Руслан Бекболотов', 'Frontend', TeamRole.FRONTEND, ''),
    ('Кузьмин Антон', 'Frontend', TeamRole.FRONTEND, ''),
    ('Джабоева Мариям', 'Frontend', TeamRole.FRONTEND, ''),
    ('Сопиев Алманбет', 'Testing/QA', TeamRole.QA, ''),
    ('Тулекова Виктория', 'Testing/QA', TeamRole.QA, ''),
]


class Command(BaseCommand):
    help = 'Синхронизирует команду проекта «Омур» со списком из таблицы'

    @transaction.atomic
    def handle(self, *args, **options):
        project = Project.objects.get(name=PROJECT)
        group = getattr(project, 'group', None)
        keep = set()

        for name, spec_name, role, note in ROSTER:
            spec = Specialization.objects.get_or_create(name=spec_name)[0]
            intern, created = Intern.objects.get_or_create(
                full_name=name,
                defaults={
                    'specialization': spec,
                    'status': InternStatus.ACTIVE,
                    'city': project.city or 'Бишкек',
                },
            )
            if created:
                self.stdout.write(f'  + человек создан: {name}')
            member = TeamMember.objects.filter(
                project=project, intern=intern,
            ).first()
            if member is None:
                member = TeamMember.objects.create(
                    project=project, group=group, intern=intern,
                    role=role, workload=50, comment=note,
                    status=TeamMember.Status.ACTIVE,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  + в команду: {name} ({member.get_role_display()})',
                ))
            else:
                member.group = group
                member.role = role
                member.comment = note
                member.status = TeamMember.Status.ACTIVE
                member.save(update_fields=[
                    'group', 'role', 'comment', 'status', 'updated_at',
                ])
            keep.add(member.pk)

        extra = project.team_members.exclude(pk__in=keep)
        for member in extra.select_related('intern'):
            self.stdout.write(self.style.WARNING(
                f'  − убран из команды: {member.intern or member.user}',
            ))
        removed = extra.count()
        extra.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Команда «{PROJECT}»: {project.team_members.count()} человек '
            f'(убрано {removed}).',
        ))
