"""ResourcePlanningService (ТЗ §14): баланс людей по направлениям."""
import datetime

from django.utils import timezone

from apps.interns.models import Intern, WORKING_STATUSES, InternStatus
from apps.resources.models import PlannedProject, PlannedProjectNeed
from apps.teams.models import TeamMember
from apps.training.models import Specialization, TrainingGroup

# Горизонт прогноза выпусков, месяцев
FORECAST_MONTHS = 3


def interns_summary() -> list[dict]:
    """По каждому направлению: всего стажёров, занято на проектах, свободно.

    Тимлиды сюда не входят — они сотрудники, а не стажёры.
    """
    from apps.teams.selectors import lead_intern_ids

    leads = lead_intern_ids()
    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    rows = []
    for spec in Specialization.objects.all():
        people = list(
            Intern.objects.active()
            .filter(specialization=spec)
            .exclude(status=InternStatus.DROPPED)
            .exclude(pk__in=leads)
            .values_list('pk', flat=True),
        )
        busy = sum(1 for pk in people if pk in busy_ids)
        rows.append({
            'specialization': spec,
            'total': len(people),
            'busy': busy,
            'free': len(people) - busy,
        })
    rows.sort(key=lambda row: -row['total'])
    return rows


def interns_total() -> dict:
    """Общий итог по стажёрам: всего, занято, свободно.

    Считается по людям, а не сложением направлений: человек без
    направления тоже попадает в общее число.
    """
    from apps.teams.selectors import lead_intern_ids

    leads = lead_intern_ids()
    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    people = list(
        Intern.objects.active()
        .exclude(status=InternStatus.DROPPED)
        .exclude(pk__in=leads)
        .values_list('pk', flat=True),
    )
    busy = sum(1 for pk in people if pk in busy_ids)
    without_spec = (
        Intern.objects.active()
        .exclude(status=InternStatus.DROPPED)
        .exclude(pk__in=leads)
        .filter(specialization__isnull=True)
        .count()
    )
    return {
        'total': len(people),
        'busy': busy,
        'free': len(people) - busy,
        'without_spec': without_spec,
        'leads': len(leads),
    }


def resource_balance(today: datetime.date | None = None) -> list[dict]:
    """Таблица баланса: Направление | Доступно | Выпуск | Нужно | Баланс.

    - Доступно: стажёры в рабочих статусах без активного проекта
      + «готов к распределению».
    - Выпуск: прогноз перехода в стажировку из групп, заканчивающихся
      в ближайшие FORECAST_MONTHS месяцев.
    - Нужно: потребность планируемых проектов в активных статусах.
    """
    today = today or timezone.localdate()
    horizon = today + datetime.timedelta(days=30 * FORECAST_MONTHS)

    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )

    rows = []
    for spec in Specialization.objects.all():
        available = (
            Intern.objects.active()
            .filter(
                specialization=spec,
                status__in=[*WORKING_STATUSES, InternStatus.READY],
            )
            .exclude(pk__in=busy_ids)
            .count()
        )
        graduating = sum(
            group.expected_interns
            for group in TrainingGroup.objects.filter(
                specialization=spec,
                end_date__gte=today, end_date__lte=horizon,
            )
        )
        needed = sum(
            need.count
            for need in PlannedProjectNeed.objects.filter(
                specialization=spec,
                planned_project__status__in=PlannedProject.ACTIVE_STATUSES,
            )
        )
        balance = available + graduating - needed
        rows.append({
            'specialization': spec,
            'available': available,
            'graduating': graduating,
            'needed': needed,
            'balance': balance,
            'deficit': balance < 0,
        })
    return rows


def upcoming_graduations(today: datetime.date | None = None) -> list[TrainingGroup]:
    """Будущие выпуски по месяцам (ТЗ §13)."""
    today = today or timezone.localdate()
    return list(
        TrainingGroup.objects.filter(end_date__gte=today)
        .select_related('specialization')
        .order_by('end_date'),
    )
