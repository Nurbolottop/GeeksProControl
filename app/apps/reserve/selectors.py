"""Выборки для списка резерва: поиск, фильтры, сортировка."""
from django.db.models import Q

from apps.reserve.models import ReserveCandidate

# Подпись → выражение сортировки для ORM
SORT_OPTIONS = [
    ('rating', 'По рейтингу'),
    ('created', 'По дате добавления'),
    ('updated', 'По дате обновления'),
    ('name', 'По ФИО'),
]
SORT_EXPRESSIONS = {
    'rating': ('-rating', 'full_name'),
    'created': ('-created_at',),
    'updated': ('-updated_at',),
    'name': ('full_name',),
}

RATING_OPTIONS = [('9', 'от 9'), ('8', 'от 8'), ('7', 'от 7'), ('6', 'от 6')]

READINESS_OPTIONS = [
    ('looking', 'Ищет работу'),
    ('not_looking', 'Не ищет работу'),
    ('internship', 'Готов(а) к стажировке'),
    ('relocate', 'Готов(а) к переезду'),
]


def candidates(params) -> tuple:
    """Отфильтрованный список кандидатов и применённая сортировка."""
    qs = (
        ReserveCandidate.objects.active()
        .select_related('specialization', 'training_group')
    )
    search = params.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(telegram__icontains=search),
        )
    if params.get('specialization'):
        qs = qs.filter(specialization_id=params['specialization'])
    if params.get('level'):
        qs = qs.filter(geekspro_level=params['level'])
    if params.get('skill'):
        qs = qs.filter(skills__icontains=params['skill'].strip())
    if params.get('city'):
        qs = qs.filter(city=params['city'])
    if params.get('work_format'):
        qs = qs.filter(work_format=params['work_format'])
    if params.get('employment'):
        qs = qs.filter(employment_type=params['employment'])
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    readiness = params.get('readiness')
    if readiness == 'looking':
        qs = qs.filter(is_looking_for_job=True)
    elif readiness == 'not_looking':
        qs = qs.filter(is_looking_for_job=False)
    elif readiness == 'internship':
        qs = qs.filter(ready_for_internship=True)
    elif readiness == 'relocate':
        qs = qs.filter(ready_to_relocate=True)
    rating = params.get('rating', '')
    if rating.isdigit():
        qs = qs.filter(rating__gte=int(rating))

    sort = params.get('sort', 'rating')
    if sort not in SORT_EXPRESSIONS:
        sort = 'rating'
    return qs.order_by(*SORT_EXPRESSIONS[sort]), sort


def cities() -> list[str]:
    return list(
        ReserveCandidate.objects.active().exclude(city='')
        .values_list('city', flat=True).distinct().order_by('city'),
    )
