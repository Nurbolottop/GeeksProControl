"""Раунд 8: новая партия самозаполнения — 14 дублей той же природы, что
и раньше (старая карточка с проектом, но без контактов + новая анкета
с контактами, но без проекта). Разобрано вручную по email/telegram/
специализации; где в новой анкете ФИО полнее или email/telegram явно
подтверждает написание — берём его, иначе оставляем старое.

    python manage.py merge_intern_duplicates
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

MERGES = [
    (787, 875, {
        # telegram @Bayelenko подтверждает «Байэл» — ФИО старой записи не трогаем
        'phone': '0701900978', 'email': 'iyosjwhsh2@gmail.com',
        'telegram': '@Bayelenko', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 5, 29),
        'internship_start_date': datetime.date(2026, 6, 12),
    }),
    (683, 868, {
        'full_name': 'Алтынбекова Дилназ Алтынбековна',
        'phone': '+996 (707) 303-869', 'email': 'dilnazaltynbekkyzy55@gmail.com',
        'telegram': '@krolikchan', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 2, 28),
        'internship_start_date': datetime.date(2025, 6, 3),
    }),
    (722, 881, {
        'full_name': 'Бекболотова Айнарка Нургазиевна',
        'phone': '+996 708 889 032', 'email': 'ainarka11@gmail.com',
        'telegram': '@n_Aika', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 4, 30),
        'internship_start_date': datetime.date(2025, 5, 15),
    }),
    (765, 880, {
        'full_name': 'Джеенбекова Малика Айбековна',
        'phone': '0501122799', 'email': 'malikoshka000@gmail.com',
        'telegram': 'mikoshh11', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 3, 9),
        'internship_start_date': datetime.date(2026, 5, 20),
    }),
    (710, 878, {
        'full_name': 'Зарыпбеков Калысбек Бакытбекович',
        'phone': '+996990228885', 'email': 'zarypbekov.kalys@gmail.com',
        'telegram': 'xyzwerttt', 'city': 'Бишкек', 'branch': 'Бишкек',
    }),
    (718, 883, {
        'full_name': 'Исраилов Исмаил Иброхимович',
        'phone': '0226140748', 'email': 'ismailisrailov986@gmail.com',
        'city': 'Джалал-Абад', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 3, 27),
        'internship_start_date': datetime.date(2026, 6, 27),
    }),
    (775, 867, {
        'full_name': 'Кошойбаев Искандер Айбекович',
        'phone': '+996555194109', 'email': 'kosojbaeviskander@gmail.com',
        'telegram': '@black_hole_888_yt', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 7, 15),
        'internship_start_date': datetime.date(2026, 11, 20),
    }),
    (663, 877, {
        'full_name': 'Темирбаева Луиза Кыялбековна',
        'phone': '996706910473', 'email': 'luizatemirbaeva@icloud.com',
        'telegram': '@nazirbaevallu', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 3, 25),
        'internship_start_date': datetime.date(2026, 4, 3),
    }),
    (690, 874, {
        'full_name': 'Осоркулова Амина Нургазыевна',
        'phone': '+996705884963', 'email': 'anotp96@gmail.com',
        'telegram': 'awillovv', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 2, 23),
        'internship_start_date': datetime.date(2026, 9, 2),
    }),
    (764, 873, {
        # ФИО у старой записи уже верно, просто донабираем контакты
        'phone': '+996557729595', 'email': 'aidarovsabyr135@gmail.com',
        'telegram': '@sabyrfx', 'city': 'Бишкек', 'branch': 'Бишкек',
        'internship_start_date': datetime.date(2026, 6, 10),
    }),
    (795, 879, {
        'full_name': 'Тилебалиев Нурбек Айбекович',
        'phone': '0707772167', 'email': 'tilenur@gmail.com',
        'telegram': 'N_Tilebaliev', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 6, 25),
        'internship_start_date': datetime.date(2026, 9, 1),
    }),
    (711, 872, {
        'full_name': 'Аширматкулов Нурислам Насрединович',
        'phone': '996500410107', 'email': 'nurnasyrdyn@gmail.com',
        'telegram': '@User5721', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 4, 19),
        'internship_start_date': datetime.date(2026, 6, 29),
    }),
    (723, 882, {
        'full_name': 'Бекболотов Нур Нургазиевич',
        'phone': '0707379297', 'email': 'bekbolotovnur09@gmail.com',
        'telegram': '@nurxdev', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 4, 30),
        'internship_start_date': datetime.date(2025, 5, 3),
    }),
    (669, 871, {
        # email cerikkulov... подтверждает «Чериккулов» (двойное к) — берём его
        'full_name': 'Чериккулов Элмирбек Акылбекович',
        'phone': '+996 775 210 706', 'email': 'cerikkulovelmirbek0@gmail.com',
        'telegram': '@ARDENT_T', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 3, 25),
        'internship_start_date': datetime.date(2026, 4, 2),
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
