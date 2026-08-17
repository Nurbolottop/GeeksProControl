"""Собрания группы и табель посещаемости."""
import calendar
import datetime

from django.db import transaction
from django.utils import timezone

from apps.attendance.models import Attendance, GroupMeeting, MeetingKind


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)


def default_host(group, kind: str):
    """Кто проводит собрание: PM или тимлид группы — по виду собрания."""
    role = 'team_lead' if kind == MeetingKind.LEAD_INTERNS else 'pm'
    member = group.members.filter(
        role=role, status='active', intern__isnull=False,
    ).select_related('intern').first()
    return member.intern if member else None


@transaction.atomic
def create_meeting(
    group, kind: str, date: datetime.date, host=None, topic: str = '',
) -> GroupMeeting | None:
    """Создаёт одно собрание на дату. Ведущий подставляется по виду собрания.

    Возвращает None, если такое собрание уже есть.
    """
    meeting, is_new = GroupMeeting.objects.get_or_create(
        group=group, kind=kind, date=date,
        defaults={'host': host or default_host(group, kind), 'topic': topic},
    )
    return meeting if is_new else None


def build_sheet(group, year: int, month: int) -> dict:
    """Табель: строки — люди группы, колонки — собрания месяца."""
    first, last = month_bounds(year, month)
    meetings = list(
        group.meetings.filter(date__gte=first, date__lte=last)
        .order_by('date', 'kind'),
    )
    members = [
        member for member in group.members.select_related(
            'intern__specialization',
        ).order_by('role', 'intern__full_name')
        if member.intern_id
    ]

    marks = {
        (mark.intern_id, mark.meeting_id): mark
        for mark in Attendance.objects.filter(meeting__in=meetings)
    }

    rows = []
    for member in members:
        cells, attended, marked = [], 0, 0
        for meeting in meetings:
            mark = marks.get((member.intern_id, meeting.pk))
            if mark:
                marked += 1
                if mark.is_attended:
                    attended += 1
            cells.append({
                'meeting': meeting,
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

    # Сводка по видам: сколько собраний всего и сколько уже проведено
    by_kind: dict[str, dict] = {}
    for meeting in meetings:
        entry = by_kind.setdefault(meeting.kind, {
            'label': meeting.get_kind_display(), 'total': 0, 'held': 0,
        })
        entry['total'] += 1
        entry['held'] += int(meeting.status == GroupMeeting.Status.HELD)

    return {
        'meetings': meetings,
        'rows': rows,
        'rate': round(total_attended / total_marked * 100) if total_marked else None,
        'marked': total_marked,
        'by_kind': list(by_kind.values()),
    }


def toggle_mark(meeting, intern, user=None) -> Attendance | None:
    """Переключает отметку: Был → Не был → Опоздал → Уважительная → пусто."""
    mark = Attendance.objects.filter(meeting=meeting, intern=intern).first()
    if mark is None:
        # Первая отметка на собрании — считаем его проведённым
        if meeting.status == GroupMeeting.Status.PLANNED:
            meeting.status = GroupMeeting.Status.HELD
            meeting.save(update_fields=['status', 'updated_at'])
        return Attendance.objects.create(
            meeting=meeting, intern=intern,
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


@transaction.atomic
def mark_all_present(meeting, user=None) -> int:
    """Отметить всю активную команду присутствующей на собрании."""
    created = 0
    for member in meeting.group.members.filter(
        status='active',
    ).exclude(intern__isnull=True):
        _, is_new = Attendance.objects.get_or_create(
            meeting=meeting, intern=member.intern,
            defaults={'status': Attendance.Status.PRESENT, 'marked_by': user},
        )
        created += int(is_new)
    if created and meeting.status == GroupMeeting.Status.PLANNED:
        meeting.status = GroupMeeting.Status.HELD
        meeting.save(update_fields=['status', 'updated_at'])
    return created


def upcoming_meetings(group, limit: int = 5):
    today = timezone.localdate()
    return group.meetings.filter(date__gte=today).order_by('date')[:limit]
