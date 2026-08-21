"""Добавляет стажёров в команды проектов по спискам от руководителя.

Списки приходят по направлениям: фронтенд, бекенд и так далее.
ПМ и тимлиды здесь не трогаются — только стажёры направлений.

    python manage.py add_interns
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern, InternStatus
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization

# Как проект называют в переписке → как он называется в базе
ALIASES = {
    'садик': 'Балажан',
    'школа': 'БилимОрдо',
}

# (проект, направление, роль, [ФИО])
ROSTER = [
    ('садик', 'Frontend', TeamRole.FRONTEND, [
        'Нурмухамматов Мухаммадсаид',
        'Камалова Айдеми',
    ]),
    ('садик', 'Backend', TeamRole.BACKEND, [
        'Темирбаева Луиза',
        'Арапова Адалат',
        'Капаров Улар',
        'Назаров Абдурахман',
        'Абдикалилов Ислам',
        'Джалалов Фаррух',
    ]),
    ('школа', 'Frontend', TeamRole.FRONTEND, [
        'Чериикулов Элмирбек',
        'Азимова Каниет',
    ]),
    ('школа', 'Backend', TeamRole.BACKEND, [
        'Суранбаев Нурсеит',
        'Аманбаев Шермамат',
        'Султанбеков Тамерлан',
        'Кубатбек уулу Омар',
        'Азамжанов Мухамадали',
        'Эндешев Данис',
        'Маматкаримов Санжар',
        'Ташболотов Алихан',
    ]),
]


class Command(BaseCommand):
    help = 'Добавляет стажёров в команды по спискам направлений'

    @transaction.atomic
    def handle(self, *args, **options):
        added = 0
        for alias, spec_name, role, names in ROSTER:
            project_name = ALIASES.get(alias, alias)
            project = Project.objects.filter(name=project_name).first()
            if project is None:
                self.stdout.write(self.style.ERROR(
                    f'Проект «{project_name}» не найден — пропускаю {len(names)} чел.',
                ))
                continue
            group = getattr(project, 'group', None)
            spec = Specialization.objects.get_or_create(name=spec_name)[0]

            self.stdout.write(f'{project.display_code} {project.name} — {spec_name}:')
            for name in names:
                intern, created = Intern.objects.get_or_create(
                    full_name=name,
                    defaults={
                        'specialization': spec,
                        'status': InternStatus.ACTIVE,
                        'city': project.city or 'Ош',
                    },
                )
                member, made = TeamMember.objects.get_or_create(
                    project=project, intern=intern,
                    defaults={
                        'group': group, 'role': role,
                        'status': TeamMember.Status.ACTIVE,
                    },
                )
                added += int(made)
                mark = '+' if made else '=';
                self.stdout.write(
                    f'  {mark} {name}'
                    f'{" (человек создан)" if created else ""}',
                )

        self.stdout.write(self.style.SUCCESS(
            f'Добавлено в команды: {added}. '
            f'Всего людей в базе: {Intern.objects.count()}.',
        ))
