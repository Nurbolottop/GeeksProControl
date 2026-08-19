"""Недельный отчёт GeeksPro — по форме рабочей таблицы (лист «отчеты»)."""
import datetime

from apps.attendance.models import Attendance, GroupMeeting, MeetingKind
from apps.interns.models import Intern, InternStatus, WORKING_STATUSES
from apps.projects.models import Project, ProjectStatus

# Норматив сдачи проекта: 110 дней с даты подписания договора
DELIVERY_LIMIT_DAYS = 110


def week_bounds(day: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Понедельник — воскресенье недели, в которую попадает дата."""
    start = day - datetime.timedelta(days=day.weekday())
    return start, start + datetime.timedelta(days=6)


def build(week_start: datetime.date) -> dict:
    """Считает все показатели недельного отчёта."""
    first, last = week_bounds(week_start)
    projects = Project.objects.active()

    # --- Проекты в разработке ---
    active_projects = projects.filter(status=ProjectStatus.ACTIVE).count()
    signed_contracts = projects.filter(
        contract_date__gte=first, contract_date__lte=last,
    ).count()

    # --- Принятые заказчиком ---
    completed = list(
        projects.filter(
            status=ProjectStatus.COMPLETED,
            actual_end_date__gte=first, actual_end_date__lte=last,
        ),
    )
    accepted_in_time = sum(
        1 for project in completed
        if project.contract_date
        and (project.actual_end_date - project.contract_date).days <= DELIVERY_LIMIT_DAYS
    )
    accepted_late = sum(
        1 for project in completed
        if project.planned_end_date
        and project.actual_end_date > project.planned_end_date
    )

    # --- Незавершённые ---
    stopped_by_us = projects.filter(status=ProjectStatus.CANCELLED).count()
    stopped_by_client = projects.filter(status=ProjectStatus.REFUSED).count()

    # --- Стажёры ---
    interns = Intern.objects.active()
    active_interns = interns.filter(status__in=WORKING_STATUSES).count()
    new_interns = interns.filter(
        internship_start_date__gte=first, internship_start_date__lte=last,
    ).count()

    # --- Выпускники ---
    finished = interns.filter(
        status__in=[InternStatus.EMPLOYABLE, InternStatus.EMPLOYED],
    ).count()
    employed = interns.filter(status=InternStatus.EMPLOYED).count()
    resume_bank_rate = round(employed / finished * 100) if finished else None

    # --- Выбывшие ---
    dropped = interns.filter(status=InternStatus.DROPPED).count()
    paused = interns.filter(status=InternStatus.PAUSED).count()

    # --- Внутренние собрания ---
    meetings = GroupMeeting.objects.filter(
        kind=MeetingKind.INTERNAL, date__gte=first, date__lte=last,
    )
    planned_meetings = meetings.count()
    held_meetings = meetings.filter(status=GroupMeeting.Status.HELD).count()
    missed_meetings = planned_meetings - held_meetings

    marks = list(Attendance.objects.filter(meeting__in=meetings))
    attended = sum(1 for mark in marks if mark.is_attended)
    attendance_rate = round(attended / len(marks) * 100) if marks else None
    absence_rate = 100 - attendance_rate if attendance_rate is not None else None

    return {
        'projects': {
            'active': active_projects,
            'signed_contracts': signed_contracts,
        },
        'accepted': {
            'in_time': accepted_in_time,
            'late': accepted_late,
        },
        'stopped': {
            'by_us': stopped_by_us,
            'by_client': stopped_by_client,
        },
        'interns': {
            'active': active_interns,
            'new': new_interns,
        },
        'graduates': {
            'finished': finished,
            'resume_bank_rate': resume_bank_rate,
        },
        'left': {
            'dropped': dropped,
            'stopped': 0,
            'paused': paused,
        },
        'meetings': {
            'planned': planned_meetings,
            'held': held_meetings,
            'missed': missed_meetings,
            'attendance_rate': attendance_rate,
            'absence_rate': absence_rate,
        },
    }


# Структура для вывода: блок → строки (подпись, ключ, суффикс)
SECTIONS = [
    ('Проекты в разработке', 'projects', [
        ('Количество активных проектов', 'active', ''),
        ('Количество подписанных договоров на разработку', 'signed_contracts', ''),
    ]),
    ('Проекты, принятые заказчиком', 'accepted', [
        (f'Принято заказчиком за {DELIVERY_LIMIT_DAYS} дней после договора',
         'in_time', ''),
        ('Передано заказчику с просрочкой', 'late', ''),
    ]),
    ('Незавершённые проекты', 'stopped', [
        ('Прекращены по инициативе исполнителя', 'by_us', ''),
        ('Прекращены по инициативе заказчика', 'by_client', ''),
    ]),
    ('Стажёры', 'interns', [
        ('Активные стажёры', 'active', ''),
        ('Новые стажёры', 'new', ''),
    ]),
    ('Выпускники', 'graduates', [
        ('Успешно завершившие стажировку', 'finished', ''),
        ('% добавленных в банк резюме', 'resume_bank_rate', '%'),
    ]),
    ('Выбывшие из стажировки', 'left', [
        ('Отчисленные', 'dropped', ''),
        ('Прекратившие', 'stopped', ''),
        ('Приостановившие', 'paused', ''),
    ]),
    ('Внутренние собрания', 'meetings', [
        ('Запланированные', 'planned', ''),
        ('Проведённые', 'held', ''),
        ('Непроведённые', 'missed', ''),
        ('% посещаемости собраний', 'attendance_rate', '%'),
        ('% неприсутствия', 'absence_rate', '%'),
    ]),
]


def as_sections(data: dict) -> list[dict]:
    """Готовит данные отчёта к выводу блоками."""
    result = []
    for title, group_key, rows in SECTIONS:
        group = data.get(group_key, {})
        result.append({
            'title': title,
            'rows': [
                {
                    'label': label,
                    'value': group.get(key),
                    'suffix': suffix,
                }
                for label, key, suffix in rows
            ],
        })
    return result
