"""Выборки для IT-академии: выпуски по направлениям.

Академия сообщает только направление, номер группы, даты и численность,
поэтому всё считаем от дат на сегодняшний день. Смотрим на академию так
же, как она сама себя описывает, — по направлениям.
"""
import datetime

from django.utils import timezone

from apps.training.models import GroupStatus, Specialization, TrainingGroup

MONTHS_RU = [
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
MONTHS_SHORT = [
    'янв', 'фев', 'мар', 'апр', 'май', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек',
]
HORIZONS = [('6', '6 месяцев'), ('12', '12 месяцев'), ('24', '24 месяца')]


def plural(number: int, one: str, few: str, many: str) -> str:
    """1 студент, 2 студента, 5 студентов."""
    tail = number % 100
    if 11 <= tail <= 14:
        return many
    tail %= 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def students_label(count: int | None) -> str:
    if count is None:
        return 'численность неизвестна'
    return f'{count} {plural(count, "студент", "студента", "студентов")}'


def span_label(days: int) -> str:
    """Срок словами в винительном падеже: «через 1 неделю», «5 месяцев назад»."""
    days = abs(days)
    if days < 14:
        return f'{days} {plural(days, "день", "дня", "дней")}'
    if days < 60:
        weeks = round(days / 7)
        return f'{weeks} {plural(weeks, "неделю", "недели", "недель")}'
    months = round(days / 30.4)
    return f'{months} {plural(months, "месяц", "месяца", "месяцев")}'


def when_label(group, stage: str, today: datetime.date) -> str:
    """«старт через 2 недели», «выпуск через 3 месяца», «выпустилась 5 дней назад»."""
    if stage == GroupStatus.RECRUITING and group.start_date:
        days = (group.start_date - today).days
        return 'старт завтра' if days == 1 else f'старт через {span_label(days)}'
    if not group.end_date:
        return 'дата выпуска неизвестна'
    days = (group.end_date - today).days
    if stage == GroupStatus.GRADUATED:
        return f'выпустилась {span_label(days)} назад'
    if days == 0:
        return 'выпуск сегодня'
    return 'выпуск завтра' if days == 1 else f'выпуск через {span_label(days)}'


def month_label(date: datetime.date) -> str:
    return f'{MONTHS_RU[date.month - 1]} {date.year}'


def month_start(date: datetime.date) -> datetime.date:
    return date.replace(day=1)


def next_month(date: datetime.date) -> datetime.date:
    return (date.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)


def add_months(date: datetime.date, months: int) -> datetime.date:
    for _ in range(months):
        date = next_month(date)
    return date


def live_groups():
    """Все группы, кроме не состоявшихся."""
    return (
        TrainingGroup.objects.exclude(status=GroupStatus.CANCELLED)
        .select_related('specialization')
        .order_by('end_date', 'number')
    )


def matrix(months: int = 12, today: datetime.date | None = None) -> dict:
    """Сетка «направление × месяц выпуска»: сколько студентов выпускается.

    Колонки — от текущего месяца до последнего месяца с выпуском внутри
    горизонта: пустой хвост из «—» ничего не сообщает.
    """
    today = today or timezone.localdate()
    start = month_start(today)
    limit = add_months(start, months)
    groups = [
        group for group in live_groups()
        if group.end_date and start <= group.end_date < limit
    ]

    last = max((month_start(g.end_date) for g in groups), default=start)
    columns = []
    cursor = start
    while cursor <= last:
        columns.append(cursor)
        cursor = next_month(cursor)

    def empty_cell():
        return {'students': 0, 'unknown': 0, 'groups': []}

    rows = {}
    for group in groups:
        spec = group.specialization
        row = rows.setdefault(spec.pk, {
            'specialization': spec,
            'cells': {month: empty_cell() for month in columns},
            'students': 0, 'unknown': 0,
        })
        cell = row['cells'][month_start(group.end_date)]
        cell['groups'].append(group)
        if group.students_count is None:
            cell['unknown'] += 1
            row['unknown'] += 1
        else:
            cell['students'] += group.students_count
            row['students'] += group.students_count

    ordered = sorted(rows.values(), key=lambda row: (-row['students'], row['specialization'].name))
    for row in ordered:
        row['cells'] = [row['cells'][month] for month in columns]

    footer = []
    for index, month in enumerate(columns):
        footer.append({
            'students': sum(row['cells'][index]['students'] for row in ordered),
            'unknown': sum(row['cells'][index]['unknown'] for row in ordered),
        })
    return {
        'columns': [
            {'month': month, 'short': MONTHS_SHORT[month.month - 1], 'year': month.year}
            for month in columns
        ],
        'rows': ordered,
        'footer': footer,
        'students': sum(row['students'] for row in ordered),
        'unknown': sum(row['unknown'] for row in ordered),
        'groups': len(groups),
    }


def directions(today: datetime.date | None = None) -> list[dict]:
    """Направления академии с их группами — как в сообщении от академии.

    Показываем группы, которые ещё не выпустились; выпущенные за последние
    два месяца оставляем внизу списка — эти люди как раз сейчас приходят.
    """
    from apps.resources.services import interns_summary

    today = today or timezone.localdate()
    recent = _months_back(today, 2)
    soon_limit = add_months(month_start(today), 3)
    free_by_spec = {row['specialization'].pk: row['free'] for row in interns_summary()}

    result = []
    for spec in Specialization.objects.all():
        items = []
        for group in live_groups().filter(specialization=spec):
            stage = group.stage_by_dates(today)
            if stage == GroupStatus.GRADUATED and group.end_date < recent:
                continue
            items.append({
                'group': group,
                'stage': stage,
                'stage_label': GroupStatus(stage).label,
                'students': students_label(group.students_count),
                'when': when_label(group, stage, today),
            })
        if not items:
            continue
        open_items = [item for item in items if item['stage'] != GroupStatus.GRADUATED]
        result.append({
            'specialization': spec,
            'items': items,
            'studying': sum(
                item['group'].students_count or 0
                for item in open_items if item['stage'] == GroupStatus.STUDYING
            ),
            'soon': sum(
                item['group'].students_count or 0 for item in open_items
                if item['group'].end_date and item['group'].end_date < soon_limit
            ),
            'groups': len(open_items),
            'free_now': free_by_spec.get(spec.pk, 0),
        })
    result.sort(key=lambda row: (-row['studying'] - row['soon'], row['specialization'].name))
    return result


def _months_back(today: datetime.date, months: int) -> datetime.date:
    date = month_start(today)
    for _ in range(months):
        date = (date - datetime.timedelta(days=1)).replace(day=1)
    return date


def silent_directions() -> list[Specialization]:
    """Направления, по которым в академии нет ни одной живой группы."""
    with_groups = set(
        live_groups().values_list('specialization_id', flat=True),
    )
    return [spec for spec in Specialization.objects.all() if spec.pk not in with_groups]


def academy_totals(today: datetime.date | None = None) -> dict:
    """Сводка по академии: сколько учится, набирается и скоро выпустится."""
    today = today or timezone.localdate()
    groups = list(live_groups())
    studying = [g for g in groups if g.stage_by_dates(today) == GroupStatus.STUDYING]
    recruiting = [g for g in groups if g.stage_by_dates(today) == GroupStatus.RECRUITING]
    soon_limit = add_months(month_start(today), 3)
    soon = [g for g in studying + recruiting if g.end_date and g.end_date < soon_limit]
    with_fact = [
        g for g in groups
        if g.stage_by_dates(today) == GroupStatus.GRADUATED
        and g.actual_interns and g.students_count
    ]
    students = sum(g.students_count for g in with_fact)
    came = sum(g.actual_interns for g in with_fact)
    return {
        'groups': len(studying) + len(recruiting),
        'studying': sum(g.students_count or 0 for g in studying),
        'recruiting': sum(g.students_count or 0 for g in recruiting),
        'soon': sum(g.students_count or 0 for g in soon),
        'unknown': sum(1 for g in studying + recruiting if g.students_count is None),
        'conversion': round(came / students * 100) if students else None,
    }
