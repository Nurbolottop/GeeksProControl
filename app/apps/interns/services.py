"""Бизнес-логика стажёров: пересчёт рейтинга (ТЗ §12.1)."""
from decimal import Decimal

from apps.interns.models import GraduateStatus, Intern, InternEvaluation, ProfileFormLink


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
    """Стажёры со статусом выпускника («Выпускники»): на проверке или отказались.

    Источник истины — ``Intern.graduate_status``, а не сам факт наличия
    завершённого проекта в истории: как только ПМ назначает стажёра на
    новый проект (:func:`apps.interns.views.intern_project_add`), статус
    сбрасывается и человек пропадает из этого списка — даже если у него
    остаётся членство в завершённом проекте в прошлом.
    """
    from apps.projects.models import ProjectStatus
    from apps.teams.models import TeamMember

    interns = list(
        Intern.objects.filter(graduate_status__in=GraduateStatus.values)
        .select_related('specialization'),
    )
    if not interns:
        return interns

    memberships = (
        TeamMember.objects.filter(
            intern_id__in=[i.pk for i in interns],
            status=TeamMember.Status.LEFT,
            project__status=ProjectStatus.COMPLETED,
        )
        .select_related('project')
        .order_by('intern_id', '-project__actual_end_date', '-left_at')
    )
    latest_by_intern = {}
    for member in memberships:
        latest_by_intern.setdefault(member.intern_id, member)

    for intern in interns:
        member = latest_by_intern.get(intern.pk)
        intern.graduated_project = member.project if member else None
        intern.graduated_at = (
            (member.project.actual_end_date or member.left_at) if member else None
        )
    interns.sort(key=lambda i: i.graduated_at or i.created_at.date(), reverse=True)
    return interns


def decline_graduate(intern: Intern) -> None:
    """Стажёр не хочет продолжать стажировку — остаётся выпускником.

    Именно здесь ``in_resume_bank`` НЕ трогаем: попасть в банк резюме
    можно только самостоятельно, через публичную форму (ТЗ — банк резюме
    заполняется человеком сам, а не ставится ПМ галочкой). ПМ лишь
    получает готовый текст-инструкцию, которую отправляет стажёру.
    """
    intern.graduate_status = GraduateStatus.DECLINED
    intern.save(update_fields=['graduate_status', 'updated_at'])


def issue_profile_form_link(user=None, ttl_days: int | None = None) -> ProfileFormLink:
    """Выпускает новую ссылку на анкету, гася все прежние.

    Активной может быть только одна ссылка: как только выпустили новую,
    старая перестаёт открываться — в этом и смысл «непостоянной» ссылки.
    `ttl_days` — через сколько дней ссылка закроется сама; None — бессрочно,
    до замены или ручного отключения.
    """
    from datetime import timedelta

    from django.utils import timezone

    now = timezone.now()
    ProfileFormLink.objects.filter(is_active=True).update(
        is_active=False, deactivated_at=now,
    )
    return ProfileFormLink.objects.create(
        created_by=user if user and user.is_authenticated else None,
        expires_at=now + timedelta(days=ttl_days) if ttl_days else None,
    )


def active_profile_form_link() -> ProfileFormLink | None:
    """Действующая ссылка на анкету или None.

    Истёкшую по сроку гасим на месте, чтобы список и анкета одинаково
    считали её мёртвой и в панели не висела ссылка-призрак.
    """
    from django.utils import timezone

    link = ProfileFormLink.objects.filter(is_active=True).first()
    if link is not None and link.is_expired:
        link.is_active = False
        link.deactivated_at = link.deactivated_at or timezone.now()
        link.save(update_fields=['is_active', 'deactivated_at', 'updated_at'])
        return None
    return link


# --- Филиалы -------------------------------------------------------------
# В базе филиал писался импортом как есть («Ошский филиал», «Внешние
# стажёры(Биш)», у части людей пусто), поэтому значение нормализуем:
# сначала смотрим филиал, если он пустой или непонятный — город.

BRANCH_BISHKEK = 'Бишкек'
BRANCH_OSH = 'Ош'
BRANCH_UNKNOWN = 'Без филиала'
BRANCHES = (BRANCH_BISHKEK, BRANCH_OSH, BRANCH_UNKNOWN)


def branch_from_text(*values) -> str:
    """Филиал по первому осмысленному значению: «Ошский филиал» → Ош и т.д."""
    for value in values:
        if not value:
            continue
        if 'Ош' in value:
            return BRANCH_OSH
        if 'Биш' in value:
            return BRANCH_BISHKEK
    return BRANCH_UNKNOWN


def branch_of(intern: Intern) -> str:
    """Филиал стажёра одним из трёх значений BRANCHES."""
    return branch_from_text(intern.branch, intern.city)


def branch_filter(branch: str):
    """Q-фильтр по филиалу — та же логика, что и в branch_of."""
    from django.db.models import Q

    osh = Q(branch__icontains='Ош') | (Q(branch='') & Q(city__icontains='Ош'))
    bishkek = ~osh & (
        Q(branch__icontains='Биш') | (Q(branch='') & Q(city__icontains='Биш'))
    )
    if branch == BRANCH_OSH:
        return osh
    if branch == BRANCH_BISHKEK:
        return bishkek
    return ~osh & ~bishkek


def branch_summary(interns) -> dict:
    """Сколько стажёров в каждом филиале: всего, занято, свободно,
    и разбивка по направлениям."""
    from apps.teams.models import TeamMember

    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    cards = {
        name: {'branch': name, 'total': 0, 'busy': 0, 'free': 0}
        for name in BRANCHES
    }
    by_spec: dict[str, dict] = {}
    for intern in interns:
        branch = branch_of(intern)
        card = cards[branch]
        card['total'] += 1
        if intern.pk in busy_ids:
            card['busy'] += 1
        else:
            card['free'] += 1
        spec = str(intern.specialization) if intern.specialization else 'Без направления'
        row = by_spec.setdefault(
            spec, {'name': spec, 'counts': dict.fromkeys(BRANCHES, 0), 'total': 0},
        )
        row['counts'][branch] += 1
        row['total'] += 1

    # филиал, в котором никого нет, не показываем ни карточкой, ни колонкой
    visible = [name for name in BRANCHES if cards[name]['total']]
    rows = sorted(by_spec.values(), key=lambda row: -row['total'])
    for row in rows:
        row['cells'] = [row['counts'][name] for name in visible]
    totals = {
        'total': sum(card['total'] for card in cards.values()),
        'busy': sum(card['busy'] for card in cards.values()),
        'free': sum(card['free'] for card in cards.values()),
        'cells': [cards[name]['total'] for name in visible],
    }
    return {
        'branches': visible,
        'cards': [cards[name] for name in visible],
        'rows': rows,
        'totals': totals,
    }
