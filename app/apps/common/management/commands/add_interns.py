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
    'умай': 'Umai',
    'олимпийская': 'Олимпийская школа',
    'исламский': 'Исламский университет',
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
    ('садик', 'UX/UI', TeamRole.UXUI, [
        'Салиев Яхё',
        'Абдукудус',
        'Хадича',
    ]),
    ('школа', 'Frontend', TeamRole.FRONTEND, [
        'Чериикулов Элмирбек',
        'Азимова Каниет',
    ]),
    ('исламский', 'Backend', TeamRole.BACKEND, [
        'Адиев Нурсултан',
        'Азизулло Султанов',
        'Касымжанов Касым',
        # в базе записан как «Бектемиров Усен»
        'Бектемиров Усен',
        'Сайидахмад Турсунбаев',
        'Маматкаримов Санжар',
    ]),
    ('исламский', 'Frontend', TeamRole.FRONTEND, [
        'Алимбек кызы Гулиза',
        'Курбанбаев Искендер',
        # отчество допишем отдельно, в базе «Азимова Каниет»
        'Азимова Каниет',
        'Тыныбеков Эмир',
        'Мирвахидов Тохир',
        'Амантурова Фатима',
        'Керимов Раатбек',
        'Рустамжанов Мухаммадазиз',
        'Жумабаев Абай',
    ]),
    ('исламский', 'UX/UI', TeamRole.UXUI, [
        # в базе записан как «Айжаз», фамилию допишем отдельно
        'Айжаз',
        'Садибакасова Бухадича',
        'Закиров Азизбек',
        'Розиев Асилбек',
        'Кадырбеков Имаммалик',
        'Абдиламитов Шекер',
        'Шералиева Даткайм',
        'Асилбекова Айчүрөк',
        'Касымбекова Фатима',
    ]),
    ('олимпийская', 'Backend', TeamRole.BACKEND, [
        'Зарыпбеков Калысбек',
        'Аширматкулов Нур-Ислам',
        'Анарбай кызы Элнура',
        'Бектемиров Усен',
        'Аскар Арсенов',
        'Токтобеков Нурбол',
        'Киктева Ариана',
    ]),
    ('олимпийская', 'Frontend', TeamRole.FRONTEND, [
        'Элиза Атанбаева',
        'Исмаил Исраилов',
        'Нуралиев Ислам',
        'Бекеев Турат',
        'Жамбул уулу Искендер',
        'Авазалиев Нурсултан',
        # уже в базе как «Камалова Айдеми» — отчество допишем отдельно
        'Камалова Айдеми',
        # в базе записан как «Чериикулов Элмирбек»
        'Чериикулов Элмирбек',
        'Бекболотова Айнарка',
        'Нур Бекболотов',
    ]),
    ('умай', 'Testing/QA', TeamRole.QA, [
        'Нурайым',
    ]),
    ('умай', 'Backend', TeamRole.BACKEND, [
        'Артур',
        'Мухаммадали',
    ]),
    ('умай', 'Mobile', TeamRole.MOBILE, [
        'Илья',
        'Азамат',
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
