"""Разовая склейка дублей стажёров + исправление перепутанных полей
в анкете самозаполнения (сюрприз-раунд 3): общие имена без фамилии не
совпали при автопоиске, плюс пара человек перепутала местами поля.

MERGES — обычная склейка: сохраняемая запись донабирает пустые поля
из дубля, дубль удаляется (у дубля нет своих TeamMember — терять нечего).

REASSIGN_AND_MERGE — обе старые записи уже были участниками команд
(TeamMember), поэтому просто удалить нельзя — сначала переносим участие
на сохраняемую запись, потом удаляем.

FIELD_FIXES — не дубль, просто перепутанные местами поля (телефон/имя).

    python manage.py merge_intern_duplicates
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern
from apps.teams.models import TeamMember

MERGES = [
    (740, 831, {
        'phone': '0700550032', 'email': 'raatbekkerimov01@gmail.com',
        'telegram': 'raat_kerimov', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 6, 18),
        'internship_start_date': datetime.date(2026, 7, 23),
    }),
    (792, 845, {
        'phone': '+996227083029', 'email': 't7118980@gmail.com',
        'telegram': '@MIZ2Z', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2025, 11, 30),
        'internship_start_date': datetime.date(2025, 12, 14),
    }),
]

# keep_pk, [(dup_pk, {поля}), ...] — оба дубля сливаются в одну запись
REASSIGN_AND_MERGE = (
    743,
    [
        (702, {}),  # только перенос TeamMember, своих полей не добавляет
        (827, {
            'email': 'hsadibakasova@gmail.com', 'telegram': '@Khad1icha',
            'branch': 'Ош',
            'education_end_date': datetime.date(2025, 9, 30),
            'internship_start_date': datetime.date(2026, 2, 9),
        }),
    ],
)

FIELD_FIXES = [
    (826, {'full_name': 'Алибаев Нурислам', 'phone': ''}),
]


class Command(BaseCommand):
    help = 'Склеивает известные дубли стажёров и чинит перепутанные поля'

    @transaction.atomic
    def handle(self, *args, **options):
        for keep_pk, dup_pk, updates in MERGES:
            keep = Intern.objects.get(pk=keep_pk)
            dup = Intern.objects.get(pk=dup_pk)
            for field, value in updates.items():
                setattr(keep, field, value)
            keep.save()
            dup.delete()
            self.stdout.write(self.style.SUCCESS(
                f'  {dup_pk} ({dup.full_name}) → слит в {keep_pk} ({keep.full_name})',
            ))

        keep_pk, dups = REASSIGN_AND_MERGE
        keep = Intern.objects.get(pk=keep_pk)
        for dup_pk, updates in dups:
            dup = Intern.objects.get(pk=dup_pk)
            moved = TeamMember.objects.filter(intern=dup).update(intern=keep)
            for field, value in updates.items():
                setattr(keep, field, value)
            keep.save()
            name = dup.full_name
            dup.delete()
            self.stdout.write(self.style.SUCCESS(
                f'  {dup_pk} ({name}) → слит в {keep_pk} ({keep.full_name}), '
                f'перенесено участий в команде: {moved}',
            ))

        for pk, updates in FIELD_FIXES:
            obj = Intern.objects.get(pk=pk)
            for field, value in updates.items():
                setattr(obj, field, value)
            obj.save()
            self.stdout.write(self.style.SUCCESS(
                f'  {pk}: поля исправлены → {obj.full_name}',
            ))

        self.stdout.write(self.style.SUCCESS('Готово.'))
