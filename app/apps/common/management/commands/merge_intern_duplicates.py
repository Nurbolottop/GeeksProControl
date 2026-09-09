"""Разовая склейка дублей стажёров, возникших из-за анкеты самозаполнения:
имя ввели по-английски и оно не совпало по ФИО со старой кириллической
записью.

Каждая пара — (сохраняемый id, дубль-id). Сохраняемая запись уже привязана
к проектам (TeamMember), поэтому в неё донабираются только пустые поля из
дубля, дубль удаляется.

    python manage.py merge_intern_duplicates
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

# (keep_pk, duplicate_pk, {поле: значение из дубля, которое нужно донабрать})
MERGES = [
    (760, 822, {
        'phone': '+996552160269',
        'email': 'umaralapaev99@gmail.com',
        'telegram': '@iloverayka',
        'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 4, 30),
        'internship_start_date': datetime.date(2026, 5, 6),
    }),
    (717, 808, {
        'phone': '0777787406',
        'email': 'bknade6@gmail.com',
        'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 10, 1),
        'internship_start_date': datetime.date(2025, 12, 1),
    }),
]


class Command(BaseCommand):
    help = 'Склеивает известные дубли стажёров из анкеты самозаполнения'

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
        self.stdout.write(self.style.SUCCESS(f'Готово. Слито пар: {len(MERGES)}.'))
