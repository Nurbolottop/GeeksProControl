"""Раунд 7: Белеков Азамат — новая анкета (861) без проекта задублировала
старую карточку (696) с активным проектом ОБА и рейтингом 4.86. Email
дубля подтверждает имя. Город у старой записи уже указан (Ош) —
не трогаем, донабираем только пустые поля.

    python manage.py merge_intern_duplicates
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

MERGES = [
    (696, 861, {
        'phone': '0509010406', 'email': 'belekovazamat127@gmail.com',
        'telegram': '@azabvs', 'branch': 'Бишкек',
    }),
]

DELETES = []


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
