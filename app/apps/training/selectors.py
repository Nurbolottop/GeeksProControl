"""Выборки для IT-академии: план-график набора и сводки по направлениям."""
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


def plan(months: int = 12, today: datetime.date | None = None) -> list[dict]:
    """План-график: что академия выпускает по месяцам вперёд.

    Считаем только группы, которые ещё учатся или набираются: выпущенные
    уже пришли в стажёры, а не состоявшиеся не придут никогда.
    """
    today = today or timezone.localdate()
    start = month_start(today)
    buckets = {}
    cursor = start
    for _ in range(months):
        buckets[cursor] = {
            'month': cursor, 'label': month_label(cursor), 'groups': [],
            'students': 0, 'wants': 0, 'expected': 0, 'specs': {},
        }
        cursor = next_month(cursor)
    limit = cursor

    groups = (
        TrainingGroup.objects
        .filter(
            status__in=[GroupStatus.RECRUITING, GroupStatus.STUDYING],
            end_date__gte=start, end_date__lt=limit,
        )
        .select_related('specialization')
        .order_by('end_date', 'number')
    )
    for group in groups:
        bucket = buckets[month_start(group.end_date)]
        bucket['groups'].append(group)
        bucket['students'] += group.students_count
        bucket['wants'] += group.wants_internship
        bucket['expected'] += group.expected_interns
        name = str(group.specialization)
        spec = bucket['specs'].setdefault(name, {'wants': 0, 'students': 0})
        spec['wants'] += group.wants_internship
        spec['students'] += group.students_count

    rows = list(buckets.values())
    for row in rows:
        row['specs'] = sorted(
            row['specs'].items(), key=lambda item: (-item[1]['wants'], item[0]),
        )
    return rows


def plan_totals(rows) -> dict:
    return {
        'groups': sum(len(row['groups']) for row in rows),
        'students': sum(row['students'] for row in rows),
        'wants': sum(row['wants'] for row in rows),
        'expected': sum(row['expected'] for row in rows),
    }


def by_specialization(months: int = 12, today: datetime.date | None = None) -> list[dict]:
    """По направлениям: сколько учится сейчас и сколько придёт за период.

    Рядом — сколько стажёров этого направления свободно прямо сейчас,
    чтобы было видно, где дыра, а где людей и так хватает.
    """
    from apps.resources.services import interns_summary

    today = today or timezone.localdate()
    limit = month_start(today)
    for _ in range(months):
        limit = next_month(limit)

    free_by_spec = {
        str(row['specialization']): row['free'] for row in interns_summary()
    }
    rows = []
    for spec in Specialization.objects.all():
        groups = [
            group for group in
            TrainingGroup.objects.filter(specialization=spec)
            if group.is_open
        ]
        coming = [
            group for group in groups
            if group.end_date and month_start(today) <= group.end_date < limit
        ]
        rows.append({
            'specialization': spec,
            'groups': len(groups),
            'studying': sum(group.students_count for group in groups),
            'wants': sum(group.wants_internship for group in groups),
            'coming': sum(group.wants_internship for group in coming),
            'free_now': free_by_spec.get(str(spec), 0),
        })
    rows.sort(key=lambda row: (-row['studying'], str(row['specialization'])))
    return rows


def academy_totals() -> dict:
    """Сводка по академии целиком: сколько учится и сколько хотят к нам."""
    open_groups = [
        group for group in
        TrainingGroup.objects.filter(
            status__in=[GroupStatus.RECRUITING, GroupStatus.STUDYING],
        )
    ]
    graduated = TrainingGroup.objects.filter(status=GroupStatus.GRADUATED)
    students = sum(group.students_count for group in graduated)
    came = sum(group.actual_interns for group in graduated)
    return {
        'groups': len(open_groups),
        'studying': sum(group.students_count for group in open_groups),
        'wants': sum(group.wants_internship for group in open_groups),
        'expected': sum(group.expected_interns for group in open_groups),
        'conversion': round(came / students * 100) if students else None,
    }
