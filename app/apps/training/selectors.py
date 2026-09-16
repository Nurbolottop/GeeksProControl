"""Выборки для IT-академии.

Академия сообщает только направление, номер группы, даты и численность —
и показываем мы это в том же виде, в каком она присылает:

    🎨 UX/UI
    * 39 группа — старт: 09.06.2026 · конец: 06.10.2026 — 4 студента
"""
import datetime

from django.utils import timezone

from apps.training.models import GroupStatus, Specialization, TrainingGroup

# Порядок и значки — как в сообщении академии
DIRECTION_ORDER = ['UX/UI', 'Frontend', 'Backend', 'Mobile']
DIRECTION_ICONS = {
    'UX/UI': '🎨', 'Frontend': '💻', 'Backend': '⚙️', 'Mobile': '📱',
    'Testing/QA': '🧪', 'DevOps': '🛠', 'PM': '📋',
}
# Как направление называет академия, если у нас оно называется иначе
ACADEMY_NAMES = {'UX/UI': 'Design', 'Mobile': 'Flutter'}


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


def students_text(group: TrainingGroup) -> str:
    """Численность так, как её прислали: «5–7 студентов», «пока неизвестно»."""
    if group.students_note:
        return group.students_note
    if group.students_count is None:
        return 'количество студентов пока неизвестно'
    count = group.students_count
    return f'{count} {plural(count, "студент", "студента", "студентов")}'


def live_groups():
    """Все группы, кроме не состоявшихся."""
    return (
        TrainingGroup.objects.exclude(status=GroupStatus.CANCELLED)
        .select_related('specialization')
    )


def academy_list(today: datetime.date | None = None) -> list[dict]:
    """Группы по направлениям — те, что ещё учатся или набираются."""
    today = today or timezone.localdate()
    by_spec = {}
    for group in live_groups().order_by('start_date', 'number'):
        if group.stage_by_dates(today) == GroupStatus.GRADUATED:
            continue
        by_spec.setdefault(group.specialization_id, []).append(group)

    def order(spec):
        name = spec.name
        return (DIRECTION_ORDER.index(name) if name in DIRECTION_ORDER else len(DIRECTION_ORDER), name)

    result = []
    for spec in sorted(Specialization.objects.all(), key=order):
        groups = by_spec.get(spec.pk)
        if not groups:
            continue
        result.append({
            'specialization': spec,
            'icon': DIRECTION_ICONS.get(spec.name, '•'),
            'academy_name': ACADEMY_NAMES.get(spec.name, ''),
            'lines': [
                {'group': group, 'students': students_text(group)}
                for group in groups
            ],
            'students': sum(group.students_count or 0 for group in groups),
        })
    return result


def academy_totals(today: datetime.date | None = None) -> dict:
    """Одна строка итога: сколько групп и студентов сейчас в академии."""
    today = today or timezone.localdate()
    groups = [
        group for group in live_groups()
        if group.stage_by_dates(today) != GroupStatus.GRADUATED
    ]
    return {
        'groups': len(groups),
        'students': sum(group.students_count or 0 for group in groups),
        'unknown': sum(1 for group in groups if group.students_count is None),
        'students_word': plural(
            sum(group.students_count or 0 for group in groups),
            'студент', 'студента', 'студентов',
        ),
        'groups_word': plural(len(groups), 'группа', 'группы', 'групп'),
    }
