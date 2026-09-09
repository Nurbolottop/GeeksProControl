"""Разовая склейка дублей стажёров, возникших из-за анкеты самозаполнения:
номер без +996 или ФИО в другом порядке не совпал с существующей записью.

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
    (679, 812, {'branch': 'Ош'}),
    (568, 809, {}),
    (757, 810, {'branch': 'Ош'}),
    (778, 819, {
        'phone': '0556060726',
        'email': 'amantayjumabaev707@gmail.com',
        'telegram': '@Amantai_07',
        'city': 'Бишкек',
        'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 3, 25),
        'internship_start_date': datetime.date(2026, 4, 13),
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
