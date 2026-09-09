"""Бизнес-логика стажёров: пересчёт рейтинга (ТЗ §12.1)."""
from decimal import Decimal

from apps.interns.models import Intern, InternEvaluation, ProfileFormLink


def add_evaluation(evaluation: InternEvaluation) -> InternEvaluation:
    """Сохраняет оценку и пересчитывает средний рейтинг стажёра."""
    evaluation.save()
    recalculate_rating(evaluation.intern)
    return evaluation


def recalculate_rating(intern: Intern) -> None:
    evaluations = list(intern.evaluations.all())
    if evaluations:
        total = sum(Decimal(str(e.average)) for e in evaluations)
        intern.rating = round(total / len(evaluations), 2)
    else:
        intern.rating = None
    intern.save(update_fields=['rating', 'updated_at'])


def graduated_interns() -> list[Intern]:
    """Стажёры, вышедшие из команды завершённого проекта («Выпускники»).

    По каждому стажёру берём самое позднее такое членство — человек
    мог выпуститься не с одного проекта.
    """
    from apps.projects.models import ProjectStatus
    from apps.teams.models import TeamMember

    memberships = (
        TeamMember.objects.filter(
            intern__isnull=False,
            status=TeamMember.Status.LEFT,
            project__status=ProjectStatus.COMPLETED,
        )
        .select_related('project', 'intern__specialization')
        .order_by('intern_id', '-project__actual_end_date', '-left_at')
    )
    latest_by_intern = {}
    for member in memberships:
        latest_by_intern.setdefault(member.intern_id, member)

    interns = []
    for member in latest_by_intern.values():
        intern = member.intern
        intern.graduated_project = member.project
        intern.graduated_at = member.project.actual_end_date or member.left_at
        interns.append(intern)
    interns.sort(key=lambda i: i.graduated_at or i.created_at.date(), reverse=True)
    return interns


def issue_profile_form_link(user=None) -> ProfileFormLink:
    """Выпускает новую ссылку на анкету, гася все прежние.

    Активной может быть только одна ссылка: как только выпустили новую,
    старая перестаёт открываться — в этом и смысл «непостоянной» ссылки.
    """
    from django.utils import timezone

    ProfileFormLink.objects.filter(is_active=True).update(
        is_active=False, deactivated_at=timezone.now(),
    )
    return ProfileFormLink.objects.create(
        created_by=user if user and user.is_authenticated else None,
    )


def active_profile_form_link() -> ProfileFormLink | None:
    """Действующая ссылка на анкету или None, если её ещё не выпускали."""
    return ProfileFormLink.objects.filter(is_active=True).first()
