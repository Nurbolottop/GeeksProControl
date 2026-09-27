"""Выгрузка резерва кадров в общую Google-таблицу.

Таблицу смотрят те, кто работает с кандидатами вне платформы, поэтому при
каждом изменении резерва мы переписываем её целиком: строки всегда
отсортированы по направлениям, а выбывшие кандидаты не остаются висеть.

Без ключа сервисного аккаунта модуль молча ничего не делает — платформа не
должна падать из-за внешней таблицы.
"""
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

# Одна выгрузка на запрос: таблица всё равно переписывается целиком.
_pending = threading.local()

# Колонки таблицы — в том же порядке, что уже заведён в ней руками.
HEADER = [
    '№', 'ФИО', 'Направление', 'Конец стажировки',
    'Номер телефона', 'TG username', 'Статус',
]

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
API = 'https://sheets.googleapis.com/v4/spreadsheets'

NO_DIRECTION = 'Без направления'


def is_configured() -> bool:
    """Есть ли всё, чтобы писать в таблицу."""
    import os

    path = getattr(settings, 'GOOGLE_SHEETS_CREDENTIALS_FILE', '')
    sheet = getattr(settings, 'RESERVE_SHEET_ID', '')
    return bool(path and sheet and os.path.exists(path))


def direction_of(candidate) -> str:
    """Направление кандидата так, как его писать в таблице."""
    if candidate.specialization_id and candidate.specialization:
        return candidate.specialization.name
    if candidate.direction_other:
        return candidate.direction_other
    if candidate.study_specialization_id and candidate.study_specialization:
        return candidate.study_specialization.name
    return NO_DIRECTION


def candidates_for_sheet():
    """Кого выгружаем: весь живой резерв, отсортированный по направлениям."""
    from apps.reserve.models import ReserveCandidate

    people = ReserveCandidate.objects.filter(is_archived=False).select_related(
        'specialization', 'study_specialization',
    )
    # Сортируем в Python: «Без направления» должно уезжать в конец, а не
    # вставать первым из-за пустого specialization.
    return sorted(
        people,
        key=lambda c: (
            direction_of(c) == NO_DIRECTION, direction_of(c).lower(),
            -c.priority, c.full_name.lower(),
        ),
    )


def sheet_rows(candidates=None) -> list[list[str]]:
    """Строки таблицы без заголовка. Нумерация — сквозная, как в таблице."""
    rows = []
    for number, candidate in enumerate(candidates or candidates_for_sheet(), start=1):
        telegram = (candidate.telegram or '').strip()
        rows.append([
            str(number),
            candidate.full_name,
            direction_of(candidate),
            candidate.study_end.strftime('%d.%m.%Y') if candidate.study_end else '',
            candidate.phone or '',
            telegram,
            candidate.get_status_display(),
        ])
    return rows


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=SCOPES,
    )
    return AuthorizedSession(creds)


def _tab_title(session, sheet_id: str) -> str:
    """Лист, в который пишем: из настроек или первый в таблице."""
    configured = getattr(settings, 'RESERVE_SHEET_TAB', '')
    if configured:
        return configured
    response = session.get(f'{API}/{sheet_id}?fields=sheets.properties.title')
    response.raise_for_status()
    sheets = response.json().get('sheets') or []
    if not sheets:
        raise RuntimeError('В таблице нет листов.')
    return sheets[0]['properties']['title']


def push(rows=None) -> int:
    """Переписать таблицу целиком. Возвращает число выгруженных строк."""
    sheet_id = settings.RESERVE_SHEET_ID
    rows = sheet_rows() if rows is None else rows
    session = _session()
    tab = _tab_title(session, sheet_id)
    # Сначала чистим старые данные: иначе от прошлой выгрузки останется
    # хвост, если кандидатов стало меньше.
    clear = session.post(f'{API}/{sheet_id}/values/{tab}!A1:Z10000:clear', json={})
    clear.raise_for_status()
    update = session.put(
        f'{API}/{sheet_id}/values/{tab}!A1',
        params={'valueInputOption': 'USER_ENTERED'},
        json={'values': [HEADER] + rows},
    )
    update.raise_for_status()
    return len(rows)


def sync(reason: str = '') -> bool:
    """Безопасная выгрузка: ошибки внешней таблицы только логируем."""
    if not is_configured():
        return False
    try:
        count = push()
    except Exception:
        logger.exception('Резерв кадров: не удалось обновить Google-таблицу (%s)', reason)
        return False
    logger.info('Резерв кадров: в Google-таблицу выгружено %s строк (%s)', count, reason)
    return True


def sync_later(reason: str = '') -> None:
    """Выгрузка после коммита транзакции, чтобы в таблицу попали свежие данные.

    Таблица переписывается целиком, поэтому на пачку изменений (например,
    перетаскивание порядка) хватает одной выгрузки. Работу отдаём Celery;
    если брокер недоступен, пишем таблицу на месте — медленнее, но данные
    не расходятся.
    """
    if not is_configured() or getattr(_pending, 'scheduled', False):
        return
    from django.db import transaction

    _pending.scheduled = True

    def _run():
        _pending.scheduled = False
        from apps.reserve.tasks import sync_reserve_sheet

        try:
            sync_reserve_sheet.delay(reason)
        except Exception:
            logger.warning('Резерв кадров: Celery недоступен, пишу таблицу на месте')
            sync(reason)

    transaction.on_commit(_run)
