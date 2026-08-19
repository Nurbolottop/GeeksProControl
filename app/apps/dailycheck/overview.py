"""Живые цифры для ежедневной проверки: на что смотреть сегодня."""
import datetime

from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import GroupMeeting
from apps.interns.models import Intern, InternStatus
from apps.notifications.models import Notification
from apps.projects import selectors as project_selectors
from apps.projects.models import ProjectStageKey
from apps.tasks import selectors as task_selectors
from apps.tasks.models import TaskStatus
from apps.teams.models import TeamMember


def _card(label: str, count: int, url: str, tone: str, hint: str = '') -> dict:
    return {
        'label': label, 'count': count, 'url': url,
        'tone': tone if count else 'gray', 'hint': hint,
    }


def cards(today: datetime.date | None = None) -> list[dict]:
    """Сводка цифр с ссылками — то, что надо глазами проверить."""
    today = today or timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)

    overdue = project_selectors.overdue_projects(today).count()
    inactive = project_selectors.inactive_projects().count()
    delivery = project_selectors.active_projects().filter(
        current_stage=ProjectStageKey.DELIVERY,
    ).count()
    tasks_today = task_selectors.open_tasks().filter(deadline=today).count()
    tasks_overdue = task_selectors.overdue_tasks(today).count()

    meetings_today = GroupMeeting.objects.filter(date=today).count()
    unmarked = GroupMeeting.objects.filter(
        date__lt=today, date__gte=yesterday - datetime.timedelta(days=5),
        status=GroupMeeting.Status.PLANNED,
    ).count()

    busy = set(
        TeamMember.objects.filter(status=TeamMember.Status.ACTIVE)
        .exclude(intern__isnull=True)
        .values_list('intern_id', flat=True),
    )
    free = Intern.objects.filter(status=InternStatus.ACTIVE).exclude(
        pk__in=busy,
    ).count()

    unread = Notification.objects.filter(is_read=False, is_closed=False).count()

    return [
        _card('Просрочено проектов', overdue,
              reverse('projects:list') + '?deadline=overdue', 'red'),
        _card('Без движения', inactive,
              reverse('projects:list'), 'yellow', 'нет активности несколько дней'),
        _card('На сдаче', delivery,
              reverse('projects:list') + '?view=delivery', 'blue'),
        _card('Задачи на сегодня', tasks_today,
              reverse('tasks:list'), 'blue'),
        _card('Просроченные задачи', tasks_overdue,
              reverse('tasks:list') + '?overdue=1', 'red'),
        _card('Собраний сегодня', meetings_today,
              reverse('attendance:dashboard'), 'blue'),
        _card('Собрания без отметок', unmarked,
              reverse('attendance:dashboard'), 'red',
              'прошли, но посещаемость не проставлена'),
        _card('Свободные стажёры', free,
              reverse('resources:forecast'), 'yellow', 'не заняты ни на одном проекте'),
        _card('Непрочитанные уведомления', unread,
              reverse('notifications:list'), 'yellow'),
    ]


def last_days(days: int = 7, today: datetime.date | None = None) -> list[dict]:
    """Полоска последних дней: сколько пунктов проверено в каждый."""
    from apps.dailycheck.models import CheckItem, CheckMark

    today = today or timezone.localdate()
    total = CheckItem.objects.filter(is_active=True).count()
    start = today - datetime.timedelta(days=days - 1)
    done_by_date: dict[datetime.date, int] = {}
    for mark in CheckMark.objects.filter(date__gte=start, date__lte=today,
                                         is_done=True):
        done_by_date[mark.date] = done_by_date.get(mark.date, 0) + 1

    rows = []
    for offset in range(days):
        day = start + datetime.timedelta(days=offset)
        done = done_by_date.get(day, 0)
        rows.append({
            'date': day,
            'done': done,
            'total': total,
            'is_today': day == today,
            'full': total and done >= total,
        })
    return rows
