"""Загрузка людей и предупреждение о перегрузе (ТЗ §11, §22)."""
from django.db.models import Sum
from django.utils import timezone

from apps.teams.models import TeamMember


def person_workload(*, user=None, intern=None, exclude_pk=None) -> int:
    """Суммарная загрузка человека по активным участиям в командах."""
    qs = TeamMember.objects.filter(status=TeamMember.Status.ACTIVE)
    if user is not None:
        qs = qs.filter(user=user)
    elif intern is not None:
        qs = qs.filter(intern=intern)
    else:
        return 0
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.aggregate(total=Sum('workload'))['total'] or 0


def leave_team(member: TeamMember, reason: str = '') -> None:
    """Снять человека с проекта — не удаляем запись, чтобы не терять
    историю участия, просто помечаем «Вышел» (+ причина, если её
    выбрали при снятии).
    """
    member.status = TeamMember.Status.LEFT
    member.left_at = timezone.localdate()
    if reason in TeamMember.LeftReason.values:
        member.left_reason = reason
    member.save(update_fields=['status', 'left_at', 'left_reason', 'updated_at'])


def workload_band(total: int) -> tuple[str, str]:
    """Диапазоны загрузки (ТЗ §11): (код, подпись)."""
    if total > 100:
        return 'overload', 'Перегруз'
    if total > 80:
        return 'high', 'Высокая загрузка'
    if total > 50:
        return 'normal', 'Нормальная загрузка'
    return 'free', 'Свободен'
