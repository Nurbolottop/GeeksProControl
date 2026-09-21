"""Диалог бота-выпускника в Telegram.

Вся бизнес-логика — в services.py (обычные, тестируемые функции), тут
только формулировки сообщений и разбор ответов. Состояние разговора —
только в памяти процесса (кто уже назвал ФИО, сколько раз ошибся с
телефоном): бот упал/перезапустился — человек просто начинает заново
командой /start, ничего в БД для этого не хранится.
"""
import telebot
from django.conf import settings
from django.urls import reverse
from telebot import types

from apps.graduate_bot import services

PHONE_ATTEMPTS_LIMIT = 3

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)


@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(
        message.chat.id,
        'Здравствуйте! Это бот для выпускников GeeksPro.\n\n'
        'Введите ваше ФИО, как в анкете стажёра, — я найду вас в базе.',
    )
    bot.register_next_step_handler(message, handle_name)


def handle_name(message):
    candidates = services.find_graduates(message.text or '')
    if not candidates:
        bot.send_message(
            message.chat.id,
            'Не нашли выпускника с таким именем. Проверьте написание '
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
        if attempt >= PHONE_ATTEMPTS_LIMIT:
            bot.send_message(
                message.chat.id,
                'Номер не подошёл несколько раз подряд. Обратитесь к '
                'руководителю GeeksPro.\n\nНачать заново — /start.',
            )
            return
        left = PHONE_ATTEMPTS_LIMIT - attempt
        bot.send_message(
            message.chat.id,
            f'Номер не совпадает с тем, что в анкете. Попробуйте ещё раз '
            f'(осталось попыток: {left}).',
        )
        bot.register_next_step_handler(
            message, handle_phone, intern_id=intern_id, attempt=attempt + 1,
        )
        return
    show_choice(message.chat.id, intern)


def show_choice(chat_id, intern):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            'Продолжить стажировку', callback_data=f'continue:{intern.pk}',
        ),
    )
    markup.add(
        types.InlineKeyboardButton('В банк резюме', callback_data=f'bank:{intern.pk}'),
    )
    bot.send_message(
        chat_id, f'{intern.full_name}, личность подтверждена. Что дальше?',
        reply_markup=markup,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('bank:'))
def handle_bank(call):
    bot.answer_callback_query(call.id)
    url = f'{settings.SITE_URL}{reverse("resume_bank_apply")}'
    bot.send_message(
        call.message.chat.id,
        'Чтобы попасть в банк резюме, заполните короткую анкету по ссылке — '
        f'мы будем рекомендовать вас работодателям:\n{url}',
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('continue:'))
def handle_continue(call):
    from apps.interns.models import Intern

    bot.answer_callback_query(call.id)
    intern = Intern.objects.filter(pk=int(call.data.split(':', 1)[1])).first()
    if intern is None:
        bot.send_message(call.message.chat.id, 'Что-то пошло не так — начните заново: /start.')
        return
    projects = services.eligible_projects()
    if not projects:
        bot.send_message(
            call.message.chat.id,
            'Сейчас нет проектов со свободным местом. Обратитесь к '
            'руководителю GeeksPro — он подскажет, что делать дальше.',
        )
        return
    markup = types.InlineKeyboardMarkup()
    for project in projects:
        markup.add(types.InlineKeyboardButton(
            project.name, callback_data=f'project:{intern.pk}:{project.pk}',
        ))
    bot.send_message(call.message.chat.id, 'Выберите проект:', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith('project:'))
def handle_project_choice(call):
    from apps.interns.models import Intern
    from apps.projects.models import Project

    bot.answer_callback_query(call.id)
    _, intern_id, project_id = call.data.split(':')
    intern = Intern.objects.filter(pk=int(intern_id)).first()
    project = Project.objects.filter(pk=int(project_id)).first()
    if intern is None or project is None:
        bot.send_message(call.message.chat.id, 'Что-то пошло не так — начните заново: /start.')
        return
    services.join_graduate_to_project(intern, project)
    lead = services.team_lead_contact(project, intern)
    if lead:
        contact = lead.phone or lead.telegram or 'уточните контакты у руководителя'
        lead_line = f'Напишите тимлиду {lead.full_name} ({contact}), чтобы договориться о старте.'
    else:
        lead_line = 'Тимлид проекта пока не назначен — обратитесь к руководителю GeeksPro.'
    bot.send_message(
        call.message.chat.id,
        f'Вы успешно добавлены в проект «{project.name}»! {lead_line}',
    )
