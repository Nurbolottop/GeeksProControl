"""Диалог бота-выпускника в Telegram.

Вся бизнес-логика — в services.py (обычные, тестируемые функции), тут
только формулировки сообщений и разбор ответов. Состояние разговора —
только в памяти процесса (кто уже назвал ФИО, сколько раз ошибся с
телефоном): бот упал/перезапустился — человек просто начинает заново
командой /start, ничего в БД для этого не хранится.

Кнопки — обычная reply-клавиатура (types.ReplyKeyboardMarkup), не
инлайн: нажатие присылает текст кнопки обычным сообщением, а не
callback_query, поэтому весь выбор разбирается через
register_next_step_handler (как ФИО/телефон), а не через
callback_query_handler.
"""
import telebot
import urllib3.util.connection as urllib3_connection
from django.conf import settings
from telebot import apihelper, types

from apps.graduate_bot import services

# С этого сервера до конкретного IP api.telegram.org (149.154.166.110)
# стабильно нет маршрута — похоже на проблему пиринга дата-центра, не
# лечится ни ретраями, ни пересозданием контейнера. У другого проекта на
# этом же сервере та же проблема уже решена локальным SOCKS5-релеем на
# хосте (порт 40001) — используем его же. Без TELEGRAM_PROXY_URL бот
# просто ходит напрямую (для окружений, где прямой связи достаточно).
if settings.TELEGRAM_PROXY_URL:
    apihelper.proxy = {
        'http': settings.TELEGRAM_PROXY_URL,
        'https': settings.TELEGRAM_PROXY_URL,
    }
    # Через прокси новое соединение — это TCP + SOCKS5-рукопожатие + DNS
    # (socks5h резолвит на стороне прокси) + TLS заново, на каждый вызов:
    # заметная задержка (3–5 сек на каждое сообщение) при пересоздании
    # сессии на каждый запрос. Держим сессию 5 минут — соединение
    # переиспользуется, а протухшее всё равно не живёт долго.
    apihelper.SESSION_TIME_TO_LIVE = 300
else:
    # Без прокси, напрямую — здесь ровно наоборот: если сеть на секунду
    # оборвётся, соединение в вечном пуле останется битым, и лучше
    # каждый раз новое, чем застрять на мёртвом.
    apihelper.SESSION_TIME_TO_LIVE = 0

# api.telegram.org отдаёт и IPv4, и IPv6 адрес, а у контейнера рабочего
# IPv6-маршрута нет — часть попыток соединения выбирает IPv6 и падает
# мгновенно (ENETUNREACH), вместо того чтобы попробовать IPv4. Отключаем
# IPv6 на уровне urllib3, а не чиним сеть контейнера — так же safer и не
# трогает остальные проекты на этом сервере.
urllib3_connection.HAS_IPV6 = False

# До Telegram с этого сервера идём через прокси, и он медленный: обычный
# ответ приходит за 5–15 секунд, иногда дольше. Стандартных таймаутов
# библиотеки (15/30 сек) на это не хватает — сообщение выпускнику просто
# не уходит. Даём запас и разрешаем повтор: лучше ответить с задержкой,
# чем не ответить совсем.
apihelper.CONNECT_TIMEOUT = 30
apihelper.READ_TIMEOUT = 60
apihelper.RETRY_ON_ERROR = True
apihelper.RETRY_TIMEOUT = 3
apihelper.MAX_RETRIES = 3

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)

RULES_BUTTON = 'Ознакомиться с правилами'
RULES_OK_BUTTON = 'Я ознакомлен'
LOGIN_BUTTON = 'Войти в аккаунт'
CONTINUE_BUTTON = 'Продолжить стажировку'
FINISH_BUTTON = 'Закончить стажировку'
BANK_AGREE_BUTTON = 'Я согласен'
BANK_SENT_BUTTON = 'Отправил заявку'
PLAY_BUTTON = 'Играть'

RULES_TEXT = (
    '📋 О боте и правилах\n\n'
    'Этот бот — для выпускников стажировки GeeksPro. Через него вы '
    'решаете, что делать дальше: продолжить стажировку на новом проекте '
    'или закончить её и попасть в наш банк резюме.\n\n'
    'Как это работает:\n'
    '1. Вы входите в аккаунт — называете ФИО и номер телефона, которые '
    'указывали в анкете стажёра. Так мы убеждаемся, что это действительно вы.\n'
    '2. Выбираете одно из двух: продолжить или закончить стажировку.\n'
    '3. Дальше бот подсказывает, что делать, и присылает новости по вашему выбору.\n\n'
    'Важно:\n'
    '— Выбор делается один раз и изменить его в боте нельзя. Если '
    'ошиблись — напишите руководителю GeeksPro.\n'
    '— Один аккаунт на один Telegram: войти за другого человека не получится.\n'
    '— Номер телефона нужен только для проверки личности, никуда больше он не уходит.'
)

BANK_ABOUT_TEXT = (
    '💼 Банк резюме GeeksPro\n\n'
    'Мы размещаем ваше резюме, портфолио и сертификат на нашем сайте: '
    'https://geeks.kg/direction\n\n'
    'Оттуда вы можете делиться своей страницей, а работодатели — '
    'смотреть кандидатов и выходить на вас напрямую.\n\n'
    'Если согласны, что мы публикуем ваши данные, нажмите кнопку ниже.'
)

BANK_HOWTO_TEXT = (
    'Что нужно сделать:\n\n'
    '1. Перейдите на https://geeks.kg/sign-in и зарегистрируйтесь.\n'
    '2. Заполните все данные о себе: направление, опыт, проекты, '
    'портфолио, сертификат.\n'
    '3. Отправьте заявку на сайте.\n'
    '4. Вернитесь сюда и нажмите «Отправил заявку».'
)

# Камень-ножницы-бумага: что кого бьёт и счёт по чатам. Счёт живёт до
# перезапуска бота — это игра на перерыв, хранить её в базе незачем.
GAME_MOVES = {'✊ Камень': 'rock', '✌️ Ножницы': 'scissors', '✋ Бумага': 'paper'}
GAME_BEATS = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}
GAME_LABELS = {'rock': '✊ Камень', 'scissors': '✌️ Ножницы', 'paper': '✋ Бумага'}
_game_score: dict[int, dict] = {}


def _one_button(label):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(label))
    return markup


def _choice_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(CONTINUE_BUTTON))
    markup.add(types.KeyboardButton(FINISH_BUTTON))
    return markup


def _play_markup():
    return _one_button(PLAY_BUTTON)


def _game_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(*[types.KeyboardButton(name) for name in GAME_MOVES])
    return markup


@bot.message_handler(commands=['start'])
def handle_start(message):
    """Начало: правила → вход в аккаунт. Тем, кто уже всё выбрал,
    показываем их текущее состояние — выбор менять нельзя."""
    from apps.interns.models import GraduateStatus

    chat_id = message.chat.id
    intern = services.find_by_chat_id(chat_id)

    if intern is not None and intern.graduate_status == GraduateStatus.WAITING:
        # Ждёт распределения: кнопок выбора больше нет, только игра.
        bot.send_message(
            chat_id, services.resolved_status_message(intern),
            reply_markup=_play_markup(),
        )
        return
    if intern is not None and not intern.graduate_status:
        # Выбор уже сделан (банк резюме или проект) — просто статус.
        bot.send_message(
            chat_id, services.resolved_status_message(intern),
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return

    if not services.rules_accepted(chat_id, intern):
        bot.send_message(
            chat_id,
            'Здравствуйте! Это бот для выпускников стажировки GeeksPro.\n\n'
            'Прежде чем начать, прочитайте короткие правила.',
            reply_markup=_one_button(RULES_BUTTON),
        )
        bot.register_next_step_handler(message, handle_rules_request)
        return
    send_login_offer(message, intern)


def handle_rules_request(message):
    if (message.text or '').strip() != RULES_BUTTON:
        bot.send_message(
            message.chat.id, 'Пожалуйста, воспользуйтесь кнопкой ниже.',
            reply_markup=_one_button(RULES_BUTTON),
        )
        bot.register_next_step_handler(message, handle_rules_request)
        return
    bot.send_message(message.chat.id, RULES_TEXT, reply_markup=_one_button(RULES_OK_BUTTON))
    bot.register_next_step_handler(message, handle_rules_accept)


def handle_rules_accept(message):
    if (message.text or '').strip() != RULES_OK_BUTTON:
        bot.send_message(
            message.chat.id, 'Пожалуйста, нажмите «Я ознакомлен».',
            reply_markup=_one_button(RULES_OK_BUTTON),
        )
        bot.register_next_step_handler(message, handle_rules_accept)
        return
    services.accept_rules(message.chat.id)
    bot.send_message(
        message.chat.id,
        '🎉 Поздравляем с завершением стажировки в GeeksPro!\n\n'
        'Вы прошли настоящие проекты в команде — это уже опыт, который '
        'ценят работодатели.\n\nТеперь войдите в аккаунт, чтобы продолжить.',
        reply_markup=_one_button(LOGIN_BUTTON),
    )
    bot.register_next_step_handler(message, handle_login_request)


def send_login_offer(message, intern=None):
    bot.send_message(
        message.chat.id, 'Войдите в аккаунт, чтобы продолжить.',
        reply_markup=_one_button(LOGIN_BUTTON),
    )
    bot.register_next_step_handler(message, handle_login_request)


def handle_login_request(message):
    if (message.text or '').strip() != LOGIN_BUTTON:
        bot.send_message(
            message.chat.id, 'Пожалуйста, нажмите «Войти в аккаунт».',
            reply_markup=_one_button(LOGIN_BUTTON),
        )
        bot.register_next_step_handler(message, handle_login_request)
        return
    bot.send_message(
        message.chat.id,
        'Как вас зовут? Напишите фамилию и имя — можно в любом порядке, '
        'можно только имя, я поищу по базе.',
        reply_markup=types.ReplyKeyboardRemove(),
    )
    bot.register_next_step_handler(message, handle_name)


def handle_name(message):
    candidates = services.find_graduates(message.text or '')
    if not candidates:
        bot.send_message(
            message.chat.id,
            'Такого выпускника не нашли — либо стажировка ещё не '
            'завершена, либо имя написано иначе. Попробуйте написать '
            'по-другому (например, только фамилию) или обратитесь к '
            'руководителю GeeksPro.',
        )
        bot.register_next_step_handler(message, handle_name)
        return
    if len(candidates) > 1:
        # Просить «введите полностью, как в анкете» бесполезно: человек не
        # знает, как он записан у нас. Показываем кнопками — пусть выберет.
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        for candidate in candidates:
            markup.add(types.KeyboardButton(candidate.full_name))
        bot.send_message(
            message.chat.id, 'Нашёл несколько человек. Выберите себя:',
            reply_markup=markup,
        )
        bot.register_next_step_handler(
            message, handle_name_choice, ids=[c.pk for c in candidates],
        )
        return
    ask_phone(message, candidates[0])


def handle_name_choice(message, ids):
    from apps.interns.models import Intern

    chosen = (message.text or '').strip()
    intern = Intern.objects.filter(pk__in=ids, full_name=chosen).first()
    if intern is None:
        bot.send_message(message.chat.id, 'Выберите себя кнопкой из списка ниже.')
        bot.register_next_step_handler(message, handle_name_choice, ids=ids)
        return
    ask_phone(message, intern)


def ask_phone(message, intern):
    if not intern.phone:
        # Иначе phone_matches() всегда вернёт False (сравнивать не с чем) —
        # человек бесконечно «не проходит» проверку и получает блокировку,
        # хотя дело не в номере, а в том, что его в базе просто нет.
        bot.send_message(
            message.chat.id,
            f'{intern.full_name}, в базе не указан ваш номер телефона — '
            'проверить личность автоматически не получится. Обратитесь к '
            'руководителю GeeksPro, чтобы добавили номер, и начните снова: /start.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    if services.is_phone_locked(intern):
        minutes = services.phone_lock_minutes_left(intern)
        bot.send_message(
            message.chat.id,
            f'Слишком много неверных попыток подряд. Попробуйте через '
            f'{minutes} мин или обратитесь к руководителю GeeksPro.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    bot.send_message(
        message.chat.id,
        f'{intern.full_name}, теперь введите ваш номер телефона — тот, что '
        'указывали в анкете стажёра. Формат любой.',
        reply_markup=types.ReplyKeyboardRemove(),
    )
    bot.register_next_step_handler(message, handle_phone, intern_id=intern.pk, attempt=1)


def handle_phone(message, intern_id, attempt):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(message.chat.id, 'Что-то пошло не так — начните заново: /start.')
        return
    if not services.phone_matches(intern, message.text or ''):
        if attempt >= services.PHONE_ATTEMPTS_LIMIT:
            services.lock_phone_verification(intern)
            bot.send_message(
                message.chat.id,
                'Номер не подошёл несколько раз подряд. Проверка временно '
                f'заблокирована на {services.PHONE_LOCK_MINUTES} мин. Обратитесь к '
                'руководителю GeeksPro, если это ошибка.',
            )
            return
        left = services.PHONE_ATTEMPTS_LIMIT - attempt
        bot.send_message(
            message.chat.id,
            f'Номер не совпадает с тем, что в анкете. Попробуйте ещё раз '
            f'(осталось попыток: {left}).',
        )
        bot.register_next_step_handler(
            message, handle_phone, intern_id=intern_id, attempt=attempt + 1,
        )
        return
    taken = services.chat_taken_by_other(intern, message.chat.id)
    if taken is not None:
        bot.send_message(
            message.chat.id,
            'В этом Telegram уже входил другой выпускник — '
            f'{taken.full_name}. Один аккаунт на один Telegram: войдите со '
            'своего или обратитесь к руководителю GeeksPro.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    services.remember_chat_id(intern, message.chat.id)
    show_choice(message, intern)


def show_choice(message, intern):
    projects = services.completed_projects(intern)
    if projects:
        lines = '\n'.join(f'— {m.project.name}' for m in projects)
        projects_line = f'\n\nВы завершили проекты:\n{lines}'
    else:
        projects_line = ''

    bot.send_message(
        message.chat.id,
        f'Здравствуйте, {intern.full_name}!{projects_line}\n\n'
        'Что дальше? Выбор делается один раз, изменить его в боте нельзя.',
        reply_markup=_choice_markup(),
    )
    bot.register_next_step_handler(message, handle_choice, intern_id=intern.pk)


def handle_choice(message, intern_id):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(
            message.chat.id, 'Что-то пошло не так — начните заново: /start.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    choice = (message.text or '').strip()
    if choice == FINISH_BUTTON:
        send_bank_about(message, intern)
    elif choice == CONTINUE_BUTTON:
        join_waiting_list(message, intern)
    else:
        bot.send_message(
            message.chat.id, 'Пожалуйста, воспользуйтесь кнопками ниже.',
            reply_markup=_choice_markup(),
        )
        bot.register_next_step_handler(message, handle_choice, intern_id=intern_id)


def join_waiting_list(message, intern):
    """«Продолжить стажировку» — человек попадает в базу ожидания, а
    распределяет его руководитель со страницы «Ожидают проект»."""
    services.request_next_internship(intern, message.chat.id)
    bot.send_message(
        message.chat.id,
        f'Готово, {intern.full_name}! Вы в базе ожидания следующего '
        'проекта.\n\nКак только появится свободное место, вас добавят в '
        'команду и я напишу сюда — ничего делать не нужно.\n\n'
        'А пока можем сыграть, чтобы не скучать 🙂',
        reply_markup=_play_markup(),
    )


def send_bank_about(message, intern):
    if intern.resume_bank_status:
        # Уже подавал заявку раньше — просто говорим текущий статус.
        bot.send_message(
            message.chat.id, services.resolved_status_message(intern),
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    bot.send_message(
        message.chat.id, BANK_ABOUT_TEXT,
        reply_markup=_one_button(BANK_AGREE_BUTTON),
    )
    bot.register_next_step_handler(message, handle_bank_agree, intern_id=intern.pk)


def handle_bank_agree(message, intern_id):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(message.chat.id, 'Что-то пошло не так — начните заново: /start.')
        return
    if (message.text or '').strip() != BANK_AGREE_BUTTON:
        bot.send_message(message.chat.id, 'Пожалуйста, нажмите «Я согласен».')
        send_bank_about(message, intern)
        return
    bot.send_message(
        message.chat.id, BANK_HOWTO_TEXT,
        reply_markup=_one_button(BANK_SENT_BUTTON),
    )
    bot.register_next_step_handler(message, handle_bank_sent, intern_id=intern.pk)


def handle_bank_sent(message, intern_id):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(message.chat.id, 'Что-то пошло не так — начните заново: /start.')
        return
    if (message.text or '').strip() != BANK_SENT_BUTTON:
        bot.send_message(message.chat.id, 'Пожалуйста, нажмите «Отправил заявку».')
        bot.register_next_step_handler(message, handle_bank_sent, intern_id=intern_id)
        return
    submitted = services.submit_to_resume_bank(intern, message.chat.id)
    if submitted:
        text = (
            f'Спасибо, что прошли стажировку в GeeksPro, {intern.full_name}!\n\n'
            'Ваша заявка ушла на проверку руководителю. Когда данные '
            'проверят и опубликуют, я обязательно напишу сюда. Если '
            'что-то нужно будет поправить — тоже сообщу.'
        )
    else:
        text = 'Ваше резюме уже приняли ранее — менять ничего не нужно.'
    bot.send_message(message.chat.id, text, reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda message: (message.text or '').strip() == PLAY_BUTTON)
def handle_play(message):
    _game_score.pop(message.chat.id, None)
    bot.send_message(
        message.chat.id,
        '✊✌️✋ Камень-ножницы-бумага!\n\nВыбирайте — играем до тех пор, '
        'пока не надоест. Чтобы выйти, наберите /start.',
        reply_markup=_game_markup(),
    )


@bot.message_handler(func=lambda message: (message.text or '').strip() in GAME_MOVES)
def handle_game_move(message):
    import random

    player = GAME_MOVES[(message.text or '').strip()]
    computer = random.choice(list(GAME_BEATS))
    score = _game_score.setdefault(message.chat.id, {'you': 0, 'bot': 0, 'draw': 0})
    if player == computer:
        score['draw'] += 1
        result = 'Ничья!'
    elif GAME_BEATS[player] == computer:
        score['you'] += 1
        result = 'Вы выиграли! 🎉'
    else:
        score['bot'] += 1
        result = 'Выиграл бот 🤖'
    bot.send_message(
        message.chat.id,
        f'Вы: {GAME_LABELS[player]}\nБот: {GAME_LABELS[computer]}\n\n{result}\n\n'
        f'Счёт — вы {score["you"]} : {score["bot"]} бот (ничьих: {score["draw"]})',
        reply_markup=_game_markup(),
    )


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_fallback(message):
    """Сообщение вне сценария (потерялся, написал не в ответ на вопрос
    бота) — раньше бот в этом случае просто молчал. register_next_step_handler
    перехватывает следующее сообщение раньше этого хендлера, так что сюда
    попадают только действительно «случайные» сообщения."""
    bot.send_message(
        message.chat.id,
        'Не понял сообщение. Чтобы начать сначала — наберите /start.',
    )
