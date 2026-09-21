import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Запускает бота-выпускника в Telegram (long polling, блокирующий процесс).'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError(
                'TELEGRAM_BOT_TOKEN не задан в переменных окружения — бот не запущен.',
            )
        from apps.graduate_bot.bot import bot

        self.stdout.write(self.style.SUCCESS('Бот-выпускник запущен, слушаю Telegram…'))
        # infinity_polling сама переживает обрывы связи внутри основного
        # цикла, но самый первый запрос к Telegram (например, сразу после
        # рестарта контейнера, пока сеть ещё не готова) может упасть до
        # входа в этот цикл — без skip_pending и без обёртки такой сбой
        # роняет процесс целиком вместо того, чтобы просто попробовать ещё раз.
        while True:
            try:
                bot.infinity_polling()
            except Exception as exc:  # noqa: BLE001 — бот должен пережить любой сбой связи
                self.stderr.write(self.style.WARNING(
                    f'Бот-выпускник упал ({exc!r}), перезапуск через 5 секунд…',
                ))
                time.sleep(5)
