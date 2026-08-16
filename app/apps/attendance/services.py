"""Табель посещаемости: сетка месяца и переключение отметок."""
import calendar
import datetime

from django.utils import timezone

from apps.attendance.models import Attendance


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


def month_days(year: int, month: int) -> list[dict]:
    """Дни месяца с пометкой выходных."""
    first, last = month_bounds(year, month)
    days = []
    for day in range(1, last.day + 1):
        date = datetime.date(year, month, day)
        days.append({
            'date': date,
            'day': day,
            'is_weekend': date.weekday() >= 5,
            'is_today': date == timezone.localdate(),
        })
    return days


def build_sheet(group, year: int, month: int) -> dict:
    """Табель группы за месяц: строки — люди, колонки — дни."""
    first, last = month_bounds(year, month)
    days = month_days(year, month)

    members = [
        member for member in group.members.select_related(
            'intern__specialization',
        ).order_by('role', 'intern__full_name')
        if member.intern_id
    ]

    marks = {
        (mark.intern_id, mark.date): mark
        for mark in Attendance.objects.filter(
            group=group, date__gte=first, date__lte=last,
        )
    }

    rows = []
    for member in members:
        cells, attended, marked = [], 0, 0
        for day in days:
            mark = marks.get((member.intern_id, day['date']))
            if mark:
                marked += 1
                if mark.is_attended:
                    attended += 1
            cells.append({
                'date': day['date'],
                'day': day['day'],
                'is_weekend': day['is_weekend'],
                'is_today': day['is_today'],
                'status': mark.status if mark else '',
            })
        rows.append({
            'member': member,
            'intern': member.intern,
            'cells': cells,
            'marked': marked,
            'attended': attended,
            'rate': round(attended / marked * 100) if marked else None,
        })

    total_marked = sum(row['marked'] for row in rows)
    total_attended = sum(row['attended'] for row in rows)
    return {
        'days': days,
        'rows': rows,
        'rate': round(total_attended / total_marked * 100) if total_marked else None,
        'marked': total_marked,
    }


def toggle_mark(group, intern, date: datetime.date, user=None) -> Attendance | None:
    """Переключает отметку по кругу: Был → Не был → Опоздал → Уважительная → пусто."""
    mark = Attendance.objects.filter(
        group=group, intern=intern, date=date,
    ).first()
    if mark is None:
        return Attendance.objects.create(
            group=group, intern=intern, date=date,
            status=Attendance.Status.PRESENT, marked_by=user,
        )
    cycle = Attendance.CYCLE
    index = cycle.index(mark.status) if mark.status in cycle else 0
    if index + 1 < len(cycle):
        mark.status = cycle[index + 1]
        mark.marked_by = user
        mark.save(update_fields=['status', 'marked_by', 'updated_at'])
        return mark
    mark.delete()
    return None


def mark_all_present(group, date: datetime.date, user=None) -> int:
    """Отметить всю активную команду присутствующей на дату."""
    created = 0
    for member in group.members.filter(status='active').exclude(intern__isnull=True):
        _, is_new = Attendance.objects.get_or_create(
            group=group, intern=member.intern, date=date,
            defaults={'status': Attendance.Status.PRESENT, 'marked_by': user},
        )
        created += int(is_new)
    return created
