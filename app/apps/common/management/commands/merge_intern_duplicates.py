"""Разовая склейка дублей стажёров + чистка мусорных анкет
самозаполнения (раунд 4): общие имена без фамилии не совпали при
автопоиске, плюс одна анкета-шутка на удаление.

MERGES — обычная склейка: сохраняемая запись донабирает поля из
дубля (включая ФИО, если у дубля оно полнее), дубль удаляется.

DELETES — просто мусорная запись, без пары на слияние.

    python manage.py merge_intern_duplicates
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

MERGES = [
    (805, 823, {
        'full_name': 'Сабыралиева Даяна Нурдиновна',
        'phone': '0501644171', 'email': 'dayanasabyralieva2008@gmail.com',
        'telegram': 'drpollux', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 5, 26),
        'internship_start_date': datetime.date(2026, 7, 15),
    }),
    (781, 813, {
        'full_name': 'Анарбекова Канышай Анарбековна',
        'phone': '0220519224', 'email': 'kailinshelter@gmail.com',
        'telegram': '@konEkip', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 8, 2),
        'internship_start_date': datetime.date(2026, 7, 15),
    }),
    (780, 828, {
        'full_name': 'Герасько Никита Сергеевич',
        'phone': '+996551666240', 'email': 'stirlitz.ru@gmail.com',
        'telegram': '@NikitaGerasko', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 2, 28),
        'internship_start_date': datetime.date(2026, 5, 7),
    }),
]

DELETES = [850]  # 'привет' — анкета-шутка, реальное имя неизвестно


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
