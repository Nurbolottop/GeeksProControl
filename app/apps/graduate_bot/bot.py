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

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)

CONTINUE_BUTTON = 'Продолжить стажировку'
BANK_BUTTON = 'В банк резюме'
BANK_CONFIRM_BUTTON = 'Я подтверждаю, что зарегистрировался(ась)'


def _choice_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(CONTINUE_BUTTON))
    markup.add(types.KeyboardButton(BANK_BUTTON))
    return markup


@bot.message_handler(commands=['start'])
def handle_start(message):
    intern = services.find_by_chat_id(message.chat.id)
    if intern is not None:
        if intern.graduate_status:
            # Уже проверяли телефон в этом чате, но выбор («Продолжить»/
            # «В банк резюме») ещё не сделал — не переспрашиваем ФИО и
            # телефон заново, сразу показываем тот же выбор.
            show_choice(message, intern)
        else:
            # Уже сделал выбор раньше (заявка в банк резюме или проект) —
            # показываем текущий статус вместо повторной аутентификации.
            bot.send_message(
                message.chat.id, services.resolved_status_message(intern),
                reply_markup=types.ReplyKeyboardRemove(),
            )
        return
    bot.send_message(
        message.chat.id,
        'Здравствуйте! Это бот для выпускников GeeksPro.\n\n'
        'Введите ваше ФИО, как в анкете стажёра, — я найду вас в базе.',
        reply_markup=types.ReplyKeyboardRemove(),
    )
    bot.register_next_step_handler(message, handle_name)


def handle_name(message):
    candidates = services.find_graduates(message.text or '')
    if not candidates:
        bot.send_message(
            message.chat.id,
            'Такого выпускника не нашли — либо стажировка ещё не '
            'завершена, либо имя указано неверно. Проверьте написание '
            'или обратитесь к руководителю GeeksPro.\n\nЧтобы попробовать снова — /start.',
        )
        return
    if len(candidates) > 1:
        names = '\n'.join(f'— {c.full_name}' for c in candidates)
        bot.send_message(
            message.chat.id,
            f'Нашлось несколько похожих имён:\n{names}\n\n'
            'Введите ФИО полностью, как в анкете.',
        )
        bot.register_next_step_handler(message, handle_name)
        return
    intern = candidates[0]
    if services.is_phone_locked(intern):
        minutes = services.phone_lock_minutes_left(intern)
        bot.send_message(
            message.chat.id,
            f'Слишком много неверных попыток подряд. Попробуйте снова через '
            f'{minutes} мин или обратитесь к руководителю GeeksPro.',
        )
        return
    bot.send_message(
        message.chat.id,
        f'{intern.full_name}, для проверки личности введите ваш номер телефона '
        '(тот, что указывали в анкете стажёра).',
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
        f'🎉 Поздравляем, {intern.full_name}! Вы успешно прошли стажировку '
        f'в GeeksPro.{projects_line}\n\nЧто дальше?',
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
    if choice == BANK_BUTTON:
        send_bank_instructions(message, intern)
    elif choice == CONTINUE_BUTTON:
        send_project_list(message, intern)
    else:
        bot.send_message(
            message.chat.id, 'Пожалуйста, воспользуйтесь кнопками ниже.',
            reply_markup=_choice_markup(),
        )
        bot.register_next_step_handler(message, handle_choice, intern_id=intern_id)


def send_bank_instructions(message, intern):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton(BANK_CONFIRM_BUTTON))
    bot.send_message(
        message.chat.id,
        'Чтобы попасть в банк резюме:\n\n'
        '1. Перейдите на https://geeks.kg/sign-in\n'
        '2. Зарегистрируйтесь и заполните свои данные\n'
        '3. Когда закончите — нажмите кнопку ниже',
        reply_markup=markup,
    )
    bot.register_next_step_handler(message, handle_bank_confirm, intern_id=intern.pk)


def handle_bank_confirm(message, intern_id):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(
            message.chat.id, 'Что-то пошло не так — начните заново: /start.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    if (message.text or '').strip() != BANK_CONFIRM_BUTTON:
        bot.send_message(message.chat.id, 'Пожалуйста, воспользуйтесь кнопкой ниже.')
        send_bank_instructions(message, intern)
        return
    submitted = services.submit_to_resume_bank(intern, message.chat.id)
    if submitted:
        text = (
            'Спасибо! Ваши данные отправлены на проверку руководителю '
            'GeeksPro. Мы сообщим о результате прямо здесь.'
        )
    else:
        text = 'Ваше резюме уже приняли ранее — всё в порядке, менять ничего не нужно.'
    bot.send_message(message.chat.id, text, reply_markup=types.ReplyKeyboardRemove())


def send_project_list(message, intern):
    projects = services.eligible_projects()
    if not projects:
        bot.send_message(
            message.chat.id,
            'Сейчас нет проектов со свободным местом. Обратитесь к '
            'руководителю GeeksPro — он подскажет, что делать дальше.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for project in projects:
        markup.add(types.KeyboardButton(project.name))
    bot.send_message(message.chat.id, 'Выберите проект:', reply_markup=markup)
    bot.register_next_step_handler(message, handle_project_choice, intern_id=intern.pk)


def handle_project_choice(message, intern_id):
    from apps.interns.models import Intern

    intern = Intern.objects.filter(pk=intern_id).first()
    if intern is None:
        bot.send_message(
            message.chat.id, 'Что-то пошло не так — начните заново: /start.',
            reply_markup=types.ReplyKeyboardRemove(),
        )
        return
    chosen_name = (message.text or '').strip()
    project = next(
        (p for p in services.eligible_projects() if p.name == chosen_name), None,
    )
    if project is None:
        bot.send_message(message.chat.id, 'Выберите проект из списка кнопок ниже.')
        send_project_list(message, intern)
        return
    services.join_graduate_to_project(intern, project)
    lead = services.team_lead_contact(project, intern)
    if lead:
        contact = lead.phone or lead.telegram or 'уточните контакты у руководителя'
        lead_line = f'Напишите тимлиду {lead.full_name} ({contact}), чтобы договориться о старте.'
    else:
        lead_line = 'Тимлид проекта пока не назначен — обратитесь к руководителю GeeksPro.'
    bot.send_message(
        message.chat.id,
        f'Вы успешно добавлены в проект «{project.name}»! {lead_line}',
        reply_markup=types.ReplyKeyboardRemove(),
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
