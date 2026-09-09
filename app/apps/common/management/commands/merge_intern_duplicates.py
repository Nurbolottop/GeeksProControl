"""Раунд 5: массовая склейка дублей после кампании самозаполнения.

Оказалось, что почти вся текущая "рабочая" команда (уже расставленная
по проектам) заново прошла анкету — с телефоном/почтой, которых у их
старых карточек не было. Автопоиск в profile_apply матчит только по
телефону и точному ФИО, поэтому все эти пары превратились в дубли:
старая карточка (с командой) осталась как есть, рядом появилась новая
пустая-по-проекту, но полная по контактам.

MERGES — сохраняемая запись (уже с TeamMember) донабирает контактные
поля из дубля; если у дубля ФИО полнее/точнее — берём его, иначе
оставляем как в старой записи. Дубль без своих TeamMember удаляется.

DELETES — 769 оказался чистым дублем 675 (та же команда/проект,
тот же человек, ничего уникального не теряем).

    python manage.py merge_intern_duplicates
"""
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern

MERGES = [
    (705, 818, {
        'full_name': 'Талипов Азамат Адилетович',
        'phone': '+996502997799', 'email': 'azamat20051028@gmail.com',
        'telegram': '@pontchikk', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 7, 19),
        'internship_start_date': datetime.date(2026, 5, 5),
    }),
    (675, 843, {
        'full_name': 'Азамжанов Мухамадали Абдуллаев',
        'phone': '996999303181', 'email': 'mersbrabus444@gmail.com',
        'telegram': '@Br_Only', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 1, 16),
        'internship_start_date': datetime.date(2026, 2, 1),
    }),
    (680, 817, {
        'full_name': 'Мамасаков Артур Кучанбаевич',
        'phone': '+996 709 63 25 97', 'email': 'arturkuchanbai@gmail.com',
        'telegram': 'Artur Mamasakov', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 9, 9),
        'internship_start_date': datetime.date(2026, 5, 10),
    }),
    (714, 846, {
        'full_name': 'Арсенов Аскар Арсенович',
        'phone': '0550980039', 'email': 'skrrsnv@gmail.com',
        'telegram': 'skrrsnv', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 6, 8),
        'internship_start_date': datetime.date(2026, 7, 29),
    }),
    (698, 837, {
        'full_name': 'Бекбашев Айбек Таштанбекович',
        'phone': '+996708820764', 'email': 'aibekbekbashev5@gmail.com',
        'telegram': 'Aibek. 0708820764', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 2, 25),
        'internship_start_date': datetime.date(2026, 7, 10),
    }),
    (686, 820, {
        'full_name': 'Джабоева Мариям Владимировна',
        'phone': '+996707976449', 'email': 'attoeva01@bk.ru',
        'telegram': '@mari_dzh7', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 5, 22),
        'internship_start_date': datetime.date(2026, 6, 9),
    }),
    (668, 839, {
        'full_name': 'Джалалов Фаррух Шахрухович',
        'phone': '+996997150109', 'email': 'farruhdzalalov@gmail.com',
        'telegram': '@Orbit_Zer0', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 3, 25),
        'internship_start_date': datetime.date(2026, 3, 31),
    }),
    (694, 844, {
        # email подтверждает «Rayana», а не «Назик» — берём имя из старой записи
        'full_name': 'Жигитекова Раяна',
        'phone': '996777140401', 'email': 'rayanajung123@gmail.com',
        'telegram': '@irayazh', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 8, 31),
        'internship_start_date': datetime.date(2025, 11, 24),
    }),
    (681, 825, {
        'full_name': 'Зуев Мирослав Евгеньевич',
        'phone': '0550330397',
        'email': 'logenerlogenerovic@gmail.com',  # опечатка .con -> .com
        'telegram': 'lognesqu1k', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 4, 24),
        'internship_start_date': datetime.date(2026, 5, 15),
    }),
    (768, 814, {
        'full_name': 'Ишенкулов Нурболот Жоодарбекович',
        'phone': '+996500562869', 'email': 'Nurssweg@gmail.com',
        'telegram': '@Nursweggg', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 5, 29),
        'internship_start_date': datetime.date(2026, 6, 1),
    }),
    (782, 838, {
        'full_name': 'Галмаматова Айгерим Темирбековна',
        'phone': '+996556454500', 'email': 'aigerim.galmamatova.pls@gmail.com',
        'telegram': '+996556454500', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 7, 20),
        'internship_start_date': datetime.date(2026, 9, 2),
    }),
    (693, 832, {
        'full_name': 'Кангельдиев Тимур Назарович',
        'phone': '0505500872', 'email': 'timurkangeldiev418@gmail.com',
        'telegram': '@TimurKangeldiev', 'city': 'Токмок', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 5, 13),
        'internship_start_date': datetime.date(2026, 6, 3),
    }),
    (716, 815, {
        'full_name': 'Киктева Ариана Денисовна',
        'phone': '+996555995744', 'email': 'mdmkillermdm@gmail.com',
        'telegram': '@RootSlayer', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2025, 12, 26),
        'internship_start_date': datetime.date(2026, 7, 1),
    }),
    (783, 841, {
        'full_name': 'Кириленко Ольга Викторовна',
        'phone': '+996 (504) 110 050', 'email': 'hioojig@gmail.com',
        'telegram': '@jbfyjj', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 3, 2),
        'internship_start_date': datetime.date(2026, 9, 2),
    }),
    (685, 852, {
        'full_name': 'Кузьмин Антон Евгеньевич',
        'phone': '+996 (553) 401-601', 'email': 'antonkuzmin2006men@gmail.com',
        'telegram': '@antonkuzmin_131', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 4, 22),
        'internship_start_date': datetime.date(2026, 5, 12),
    }),
    (738, 816, {
        'full_name': 'Мрвахидов Тохир Бобирович',
        'phone': '502146086', 'email': 'timurbro1202@gmail.com',
        'telegram': '@mirvahidov', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 7, 6),
        'internship_start_date': datetime.date(2026, 7, 15),
    }),
    (745, 849, {
        'full_name': 'Розиев Асилбек мухаммаджанович',
        'phone': '+996554570091', 'email': 'asadincognito@gmail.com',
        'telegram': '@aslchyk', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2025, 2, 22),
        'internship_start_date': datetime.date(2025, 1, 21),
    }),
    (687, 836, {
        'full_name': 'Сопиев Алманбет Уланбекович',
        'phone': '0501136131', 'email': 'alman.spv13@gmail.com',
        'telegram': '@spv_all', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 6, 2),
        'internship_start_date': datetime.date(2026, 7, 1),
    }),
    (737, 842, {
        'full_name': 'Тыныбеков Эмир Тыныбековчи',
        'phone': '+996709101149', 'email': 'tynybekovemir33@gmail.com',
        'telegram': '@yusp1kR', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2026, 5, 23),
        'internship_start_date': datetime.date(2026, 7, 17),
    }),
    (691, 848, {
        'full_name': 'Шактыбеков Даулет Эркинович',
        'phone': '999403090', 'email': 'dauletsaktybekov@gmail.com',
        'telegram': '@winnnqq', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 4, 17),
        'internship_start_date': datetime.date(2026, 6, 4),
    }),
    (695, 824, {
        # telegram дубля подтверждает «Ulukbek» — ФИО старой записи верное,
        # не трогаем его, донабираем только контакты
        'phone': '+79924019973', 'email': 'uabdykaparov542@gmail.com',
        'telegram': 'Ulukbek Abdykapar Uulu', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 1, 26),
        'internship_start_date': datetime.date(2026, 6, 1),
    }),
    (720, 840, {
        'full_name': 'Жамбул тегин Искендер Илимбек уулу',
        'phone': '+996 773 392 978', 'email': 'pcjambuloviskender@gmail.com',
        'telegram': '@TootYap', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2024, 12, 25),
        'internship_start_date': datetime.date(2026, 6, 30),
    }),
    (786, 854, {
        'phone': '+996 (709) 324-666', 'email': 'isabaevafatima0@gmail.com',
        'telegram': 'dory_xw', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 5, 26),
        'internship_start_date': datetime.date(2026, 6, 3),
    }),
    (793, 858, {
        'full_name': 'Касымалиев Алихан Чындыбаевич',  # опечатка «Алихаан» в старой
        'phone': '+996755757584', 'email': 'alihankasymaliev56@gmail.com',
        'telegram': '@zxcponnX', 'city': 'Ош', 'branch': 'Ош',
        'education_end_date': datetime.date(2025, 3, 13),
        'internship_start_date': datetime.date(2024, 11, 4),
    }),
    (789, 859, {
        'phone': '0995109911', 'email': 'saida.21@icloud.com',
        'telegram': '@Saida1ts', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 2, 23),
        'internship_start_date': datetime.date(2026, 4, 9),
    }),
    (806, 857, {
        'full_name': 'Батыков Ибрахим Бактыбекович',
        'phone': '0778090079', 'email': 'fourdeltaone100@gmail.com',
        'telegram': '@Ganuy_08', 'city': 'Бишкек', 'branch': 'Бишкек',
        'education_end_date': datetime.date(2026, 7, 17),
        'internship_start_date': datetime.date(2026, 9, 4),
    }),
]

DELETES = [769]  # чистый дубль 675 — то же имя, тот же проект/группа


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
