import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# telebot.infinity_polling() при сбое сама уходит в повтор всего через 3
# секунды без остановки — на нагруженном хосте с потерей пакетов это
# вылилось в тысячи попыток за сутки с одного и того же IP подряд, и это
# подозрительно похоже на то, что сеть/Telegram начали этот IP душить как
# спамера. Поэтому здесь — свой цикл поверх обычного polling(non_stop=False)
# с растущей паузой: 10с, 20с, … максимум 2 минуты между попытками.
RETRY_START_SECONDS = 10
RETRY_MAX_SECONDS = 120


def _hide_token(message: str) -> str:
    """requests/urllib3 кладут токен прямо в текст ошибки (URL запроса) —
    прячем его перед тем, как это попадёт в логи контейнера."""
    token = settings.TELEGRAM_BOT_TOKEN
    if token and token in message:
        secret = token.split(':', 1)[-1]
        message = message.replace(secret, '*' * len(secret))
    return message


class Command(BaseCommand):
    help = 'Запускает бота-выпускника в Telegram (long polling, блокирующий процесс).'

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError(
                'TELEGRAM_BOT_TOKEN не задан в переменных окружения — бот не запущен.',
            )
        from apps.graduate_bot.bot import bot

        self.stdout.write(self.style.SUCCESS('Бот-выпускник запущен, слушаю Telegram…'))
        delay = RETRY_START_SECONDS
        while True:
            try:
                bot.polling(non_stop=False, skip_pending=True, timeout=20, long_polling_timeout=20)
            except Exception as exc:  # noqa: BLE001 — бот должен пережить любой сбой связи
                message = _hide_token(str(exc))
                self.stderr.write(self.style.WARNING(
                    f'Бот-выпускник: сбой связи ({type(exc).__name__}: {message}), '
                    f'новая попытка через {delay} сек…',
                ))
                time.sleep(delay)
                delay = min(delay * 2, RETRY_MAX_SECONDS)
            else:
                # polling() вышел сам (например, вызвали bot.stop_polling())
                # — это штатная остановка, не ошибка, пауза не нужна.
                delay = RETRY_START_SECONDS
