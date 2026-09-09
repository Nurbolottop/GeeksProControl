"""Раунд 6: найдено через аудит «статус активный без проекта».

Абдылдаева Алия Тельмановна — новая анкета без проекта, а её старая
карточка (767) стоит в двух командах, просто ФИО в анкете полнее.
790 «Бахридинова Саида Ахуновна» — пустая карточка-дубль (ни одного
своего поля), настоящие данные уже слиты в 789 в прошлом раунде.

    python manage.py merge_intern_duplicates
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

MERGES = [
    (767, 788, {
        'full_name': 'Абдылдаева Алия Тельмановна',
        'phone': '0701450594', 'email': 'aliyaabdyldaeva918@gmail.com',
        'telegram': '@a1imai', 'city': 'Бишкек', 'branch': 'Бишкек',
    }),
]

DELETES = [790]


class Command(BaseCommand):
    help = 'Склеивает известные дубли стажёров и чистит мусорные анкеты'

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

        for pk in DELETES:
            obj = Intern.objects.get(pk=pk)
            name = obj.full_name
            obj.delete()
            self.stdout.write(self.style.SUCCESS(f'  {pk} ({name}) удалён(а)'))

        self.stdout.write(self.style.SUCCESS('Готово.'))
