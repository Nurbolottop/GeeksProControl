"""Выборки для IT-академии: план-график выпусков и сводки по направлениям.

Академия сообщает только направление, номер группы, даты и численность,
поэтому всё считаем от дат на сегодняшний день, а «хотят на стажировку» и
прогноз показываем, только если их кто-то внёс.
"""
import datetime

from django.utils import timezone

from apps.training.models import GroupStatus, Specialization, TrainingGroup

MONTHS_RU = [
    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь',
]
HORIZONS = [('6', '6 месяцев'), ('12', '12 месяцев'), ('24', '24 месяца')]


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
    )


def plan(months: int = 12, today: datetime.date | None = None) -> list[dict]:
    """План-график: какие группы академия выпускает по месяцам вперёд."""
    today = today or timezone.localdate()
    start = month_start(today)
    buckets = {}
    cursor = start
    for _ in range(months):
        buckets[cursor] = {
            'month': cursor, 'label': month_label(cursor), 'groups': [],
            'students': 0, 'unknown': 0, 'wants': 0, 'expected': 0, 'specs': {},
        }
        cursor = next_month(cursor)

    groups = live_groups().filter(
        end_date__gte=start, end_date__lt=cursor,
    ).order_by('end_date', 'specialization__name', 'number')
    for group in groups:
        bucket = buckets[month_start(group.end_date)]
        bucket['groups'].append(group)
        if group.students_count is None:
            bucket['unknown'] += 1
        bucket['students'] += group.students_count or 0
        bucket['wants'] += group.wants_internship
        bucket['expected'] += group.expected_interns
        name = str(group.specialization)
        bucket['specs'][name] = bucket['specs'].get(name, 0) + (group.students_count or 0)

    rows = list(buckets.values())
    for row in rows:
        row['specs'] = sorted(row['specs'].items(), key=lambda item: (-item[1], item[0]))
    return rows


def plan_totals(rows) -> dict:
    return {
        'groups': sum(len(row['groups']) for row in rows),
        'students': sum(row['students'] for row in rows),
        'unknown': sum(row['unknown'] for row in rows),
        'wants': sum(row['wants'] for row in rows),
        'expected': sum(row['expected'] for row in rows),
    }


def by_specialization(months: int = 12, today: datetime.date | None = None) -> list[dict]:
    """По направлениям: сколько учится и сколько выпустится за период.

    Рядом — сколько стажёров этого направления свободно прямо сейчас,
    чтобы было видно, где дыра, а где людей и так хватает.
    """
    from apps.resources.services import interns_summary

    today = today or timezone.localdate()
    start = month_start(today)
    limit = add_months(start, months)
    free_by_spec = {
        str(row['specialization']): row['free'] for row in interns_summary()
    }
    groups = [group for group in live_groups() if group.is_open]

    rows = []
    for spec in Specialization.objects.all():
        own = [group for group in groups if group.specialization_id == spec.pk]
        studying = [g for g in own if g.stage == GroupStatus.STUDYING]
        graduating = [
            g for g in own if g.end_date and start <= g.end_date < limit
        ]
        rows.append({
            'specialization': spec,
            'groups': len(own),
            'studying': sum(g.students_count or 0 for g in studying),
            'recruiting': sum(
                g.students_count or 0 for g in own if g.stage == GroupStatus.RECRUITING
            ),
            'graduating': sum(g.students_count or 0 for g in graduating),
            'wants': sum(g.wants_internship for g in graduating),
            'free_now': free_by_spec.get(str(spec), 0),
        })
    rows.sort(key=lambda row: (-(row['studying'] + row['recruiting']), str(row['specialization'])))
    return rows


def academy_totals(today: datetime.date | None = None) -> dict:
    """Сводка по академии: сколько учится, набирается и скоро выпустится."""
    today = today or timezone.localdate()
    groups = list(live_groups())
    studying = [g for g in groups if g.stage_by_dates(today) == GroupStatus.STUDYING]
    recruiting = [g for g in groups if g.stage_by_dates(today) == GroupStatus.RECRUITING]
    soon_limit = add_months(month_start(today), 3)
    soon = [
        g for g in studying + recruiting
        if g.end_date and g.end_date < soon_limit
    ]
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
        'wants': sum(g.wants_internship for g in studying + recruiting),
        'unknown': sum(1 for g in studying + recruiting if g.students_count is None),
        'conversion': round(came / students * 100) if students else None,
    }
