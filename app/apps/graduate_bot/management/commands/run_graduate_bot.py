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
        bot.infinity_polling(skip_pending=True)
