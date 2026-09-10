"""Бизнес-логика резерва кадров.

Здесь всё, что должно происходить автоматически: пересчёт рейтинга,
запись истории, смена статусов при рекомендациях. Views остаются
тонкими и не дублируют эту логику.
"""
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.reserve.models import (
    CandidateStatus, EventKind, RecommendationStatus, ReserveCandidate,
    ReserveEvent, ReserveInvite,
)

# Результат по рекомендации двигает и статус самого кандидата
STATUS_BY_RECOMMENDATION = {
    RecommendationStatus.SENT: CandidateStatus.PROPOSED,
    RecommendationStatus.REVIEW: CandidateStatus.PROPOSED,
    RecommendationStatus.INTERVIEW: CandidateStatus.INTERVIEW,
    RecommendationStatus.OFFER: CandidateStatus.OFFER,
    RecommendationStatus.HIRED: CandidateStatus.EMPLOYED,
}


def log_event(candidate, kind, title, *, detail='', user=None) -> ReserveEvent:
    """История кандидата: пишем всегда, не удаляем никогда."""
    return ReserveEvent.objects.create(
        candidate=candidate, kind=kind, title=title, detail=detail,
        user=user if user and user.is_authenticated else None,
    )


def recalculate_rating(candidate: ReserveCandidate) -> None:
    """Общий рейтинг — среднее по выставленным критериям (шкала 1–10)."""
    scores = [
        getattr(candidate, field)
        for field, _ in ReserveCandidate.EVALUATION_CRITERIA
        if getattr(candidate, field) is not None
    ]
    if scores:
        total = sum(Decimal(str(s)) for s in scores)
        candidate.rating = round(total / len(scores), 2)
    else:
        candidate.rating = None
    candidate.save(update_fields=['rating', 'updated_at'])


def create_candidate(candidate: ReserveCandidate, user=None) -> ReserveCandidate:
    candidate.created_by = candidate.created_by or (
        user if user and user.is_authenticated else None
    )
    candidate.updated_by = user if user and user.is_authenticated else None
    candidate.save()
    log_event(
        candidate, EventKind.CREATED, 'Кандидат добавлен в резерв',
        detail=f'Статус: {candidate.get_status_display()}', user=user,
    )
    return candidate


def update_candidate(candidate: ReserveCandidate, user=None, detail='') -> ReserveCandidate:
    candidate.updated_by = user if user and user.is_authenticated else None
    candidate.save()
    log_event(candidate, EventKind.UPDATED, 'Данные кандидата изменены',
              detail=detail, user=user)
    return candidate


def change_status(candidate: ReserveCandidate, status: str, *, comment='', user=None):
    """Смена статуса с записью в историю. Прежние записи остаются."""
    if status == candidate.status:
        return candidate
    was = candidate.get_status_display()
    candidate.status = status
    candidate.status_changed_at = timezone.now()
    candidate.updated_by = user if user and user.is_authenticated else None
    candidate.save(update_fields=[
        'status', 'status_changed_at', 'updated_by', 'updated_at',
    ])
    log_event(
        candidate, EventKind.STATUS,
        f'Статус: {was} → {candidate.get_status_display()}',
        detail=comment, user=user,
    )
    return candidate


def save_evaluation(candidate: ReserveCandidate, user=None) -> ReserveCandidate:
    """Сохранение внутренней оценки: пересчёт рейтинга + история."""
    candidate.updated_by = user if user and user.is_authenticated else None
    candidate.save()
    recalculate_rating(candidate)
    parts = [f'{label}: {value}' for label, value in candidate.scores if value]
    if candidate.decision:
        parts.append(f'Решение: {candidate.get_decision_display()}')
    if candidate.geekspro_level:
        parts.append(f'Уровень: {candidate.get_geekspro_level_display()}')
    log_event(
        candidate, EventKind.EVALUATED,
        f'Внутренняя оценка: {candidate.rating or "—"} / 10',
        detail='; '.join(parts), user=user,
    )
    return candidate


def issue_invite(
    candidate=None, *, user=None, ttl_days: int | None = 7, recipient='',
) -> ReserveInvite:
    """Персональная ссылка на анкету.

    Для кандидата активной может быть только одна ссылка: выпуск новой
    гасит прежние, чтобы старое приглашение не гуляло по чатам.
    """
    if candidate is not None:
        ReserveInvite.objects.filter(
            candidate=candidate, is_active=True,
        ).update(is_active=False)
    invite = ReserveInvite.objects.create(
        candidate=candidate,
        recipient=recipient or (candidate.full_name if candidate else ''),
        created_by=user if user and user.is_authenticated else None,
        expires_at=timezone.now() + timedelta(days=ttl_days) if ttl_days else None,
    )
    if candidate is not None:
        log_event(
            candidate, EventKind.INVITED, 'Отправлена ссылка на анкету',
            detail=invite.get_absolute_url(), user=user,
        )
    return invite


def accept_application(invite: ReserveInvite, candidate: ReserveCandidate):
    """Кандидат отправил анкету: карточка «На проверке».

    Ссылка при этом не гаснет — она персональная и живёт до своего срока
    (или пока её не отключат вручную), чтобы человек мог вернуться и
    дополнить анкету. Повторная отправка обновляет ту же карточку.
    """
    now = timezone.now()
    candidate.submitted_at = now
    candidate.consent_at = candidate.consent_at or now
    is_new = candidate.pk is None
    candidate.save()
    if invite is not None:
        invite.candidate = candidate
        invite.used_at = invite.used_at or now
        invite.save(update_fields=['candidate', 'used_at', 'updated_at'])
    if is_new:
        log_event(candidate, EventKind.CREATED, 'Кандидат добавлен через анкету')
        log_event(
            candidate, EventKind.SUBMITTED, 'Кандидат заполнил анкету',
            detail='Согласие на передачу данных работодателям получено',
        )
    else:
        log_event(candidate, EventKind.SUBMITTED, 'Кандидат обновил свою анкету')
    # Уже проверенного человека повторная правка анкеты не отбрасывает
    # назад по статусу — только новые и ещё не проверенные.
    if candidate.status in {CandidateStatus.NEW, CandidateStatus.REVIEW}:
        change_status(candidate, CandidateStatus.REVIEW, comment='Анкета отправлена кандидатом')
    return candidate


def add_recommendation(recommendation, user=None):
    """Рекомендация компании + автоматический перевод кандидата в статус."""
    recommendation.created_by = user if user and user.is_authenticated else None
    recommendation.save()
    candidate = recommendation.candidate
    log_event(
        candidate, EventKind.RECOMMENDED,
        f'Рекомендован(а) компании: {recommendation.company_title}',
        detail=' · '.join(filter(None, [
            recommendation.vacancy,
            f'{recommendation.sent_on:%d.%m.%Y}',
            recommendation.comment,
        ])),
        user=user,
    )
    target = STATUS_BY_RECOMMENDATION.get(recommendation.status)
    if target and candidate.status in {
        CandidateStatus.NEW, CandidateStatus.REVIEW, CandidateStatus.RESERVE,
    }:
        change_status(candidate, target, comment='Автоматически по рекомендации', user=user)
    return recommendation


def update_recommendation_status(recommendation, status: str, *, comment='', user=None):
    """Результат по рекомендации: пишем в историю и двигаем статус кандидата."""
    was = recommendation.get_status_display()
    recommendation.status = status
    if comment:
        recommendation.comment = comment
    recommendation.save(update_fields=['status', 'comment', 'updated_at'])
    candidate = recommendation.candidate
    log_event(
        candidate, EventKind.REC_STATUS,
        f'{recommendation.company_title}: {was} → {recommendation.get_status_display()}',
        detail=comment, user=user,
    )
    target = STATUS_BY_RECOMMENDATION.get(status)
    if target:
        change_status(candidate, target, comment='Автоматически по рекомендации', user=user)
    elif status in {
        RecommendationStatus.COMPANY_REJECT, RecommendationStatus.CANDIDATE_REJECT,
    } and candidate.status in {CandidateStatus.PROPOSED, CandidateStatus.INTERVIEW}:
        change_status(
            candidate, CandidateStatus.RESERVE,
            comment='Вернулся в резерв после отказа', user=user,
        )
    return recommendation


def candidate_from_intern(intern, user=None) -> ReserveCandidate:
    """Завести кандидата из карточки стажёра, не перепечатывая данные."""
    existing = ReserveCandidate.objects.filter(intern=intern).first()
    if existing is not None:
        return existing
    candidate = ReserveCandidate(
        intern=intern,
        full_name=intern.full_name,
        phone=intern.phone,
        email=intern.email,
        telegram=intern.telegram,
        city=intern.city,
        specialization=intern.specialization,
        training_group=intern.training_group,
        study_specialization=intern.specialization,
        study_end=intern.education_end_date,
    )
    return create_candidate(candidate, user)


# Группы направлений — по ним анкета решает, какие ссылки показывать
# (GitHub разработчику, Behance дизайнеру) и какие примеры навыков давать.
DIRECTION_KEYWORDS = [
    ('design', ('ux', 'ui', 'дизайн', 'design', 'graphic')),
    ('qa', ('qa', 'test', 'тест')),
    ('pm', ('pm', 'project', 'менедж', 'product')),
    ('dev', ('backend', 'frontend', 'mobile', 'devops', 'разраб', 'ios', 'android')),
]


def direction_group(name: str) -> str:
    """К какой группе относится направление: dev / design / qa / pm / other."""
    lowered = (name or '').lower()
    for group, keywords in DIRECTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return group
    return 'other'


def direction_groups_map() -> dict:
    """id направления → группа, для показа нужных вопросов в анкете."""
    from apps.training.models import Specialization

    return {
        str(spec.pk): direction_group(spec.name)
        for spec in Specialization.objects.all()
    }
