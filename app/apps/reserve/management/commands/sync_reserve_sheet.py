"""Выгрузка резерва кадров в общую Google-таблицу вручную.

Без --apply только показывает, что уйдёт в таблицу — удобно проверить
сортировку по направлениям и доступ сервисного аккаунта.
"""
from django.core.management.base import BaseCommand

from apps.reserve import gsheets


class Command(BaseCommand):
    help = 'Переписать общую Google-таблицу резерва кадров (по умолчанию — предпросмотр).'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать в таблицу.')
        parser.add_argument(
            '--limit', type=int, default=20,
            help='Сколько строк показать в предпросмотре (0 — все).',
        )

    def handle(self, *args, **options):
        rows = gsheets.sheet_rows()
        self.stdout.write(f'Кандидатов к выгрузке: {len(rows)}')
        shown = rows if not options['limit'] else rows[:options['limit']]
        for row in shown:
            self.stdout.write(' | '.join(row))
        if len(shown) < len(rows):
            self.stdout.write(f'… и ещё {len(rows) - len(shown)}')

        if not gsheets.is_configured():
            self.stdout.write(self.style.WARNING(
                'Google-таблица не настроена: нужны GOOGLE_SHEETS_CREDENTIALS_FILE '
                '(файл ключа сервисного аккаунта) и RESERVE_SHEET_ID.'
            ))
            return
        if not options['apply']:
            self.stdout.write('Предпросмотр. Для записи в таблицу: --apply')
            return
        count = gsheets.push(rows)
        self.stdout.write(self.style.SUCCESS(f'В таблицу записано строк: {count}'))
