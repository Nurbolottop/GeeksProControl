"""Выборки по командам: разбивка состава по направлениям."""
from apps.teams.models import TeamMember, TeamRole

# Порядок направлений в составе команды
ROLE_ORDER = [
    TeamRole.PROJECT_MANAGER,
    TeamRole.TEAM_LEAD,
    TeamRole.UXUI,
    TeamRole.BACKEND,
    TeamRole.FRONTEND,
    TeamRole.MOBILE,
    TeamRole.QA,
    TeamRole.OTHER,
]

# Цветовые метки направлений (классы бейджей)
ROLE_TONE = {
    TeamRole.PROJECT_MANAGER: 'blue',
    TeamRole.TEAM_LEAD: 'orange',
    TeamRole.UXUI: 'yellow',
    TeamRole.BACKEND: 'green',
    TeamRole.FRONTEND: 'blue',
    TeamRole.MOBILE: 'orange',
    TeamRole.QA: 'red',
    TeamRole.OTHER: 'gray',
}

ROLE_LABELS = dict(TeamRole.choices)


# Направления, которые показываем всегда — даже когда там пусто
ALWAYS_SHOWN = [
    TeamRole.PROJECT_MANAGER,
    TeamRole.TEAM_LEAD,
    TeamRole.UXUI,
    TeamRole.BACKEND,
    TeamRole.FRONTEND,
    TeamRole.QA,
]


def group_by_role(members) -> list[dict]:
    """Разбивает состав команды на секции по направлениям.

    Пустые направления из ALWAYS_SHOWN тоже возвращаются — в каждую
    секцию добавляют людей отдельной кнопкой.
    """
    buckets: dict[str, list[TeamMember]] = {}
    for member in members:
        buckets.setdefault(member.role, []).append(member)

    sections = []
    for role in ROLE_ORDER:
        people = buckets.pop(role, [])
        if people or role in ALWAYS_SHOWN:
            sections.append({
                'role': role,
                'label': ROLE_LABELS.get(role, role),
                'tone': ROLE_TONE.get(role, 'gray'),
                'members': people,
                'count': len(people),
                'active': sum(1 for m in people if m.status == 'active'),
            })
    # Роли вне справочника — в конец
    for role, people in buckets.items():
        sections.append({
            'role': role, 'label': ROLE_LABELS.get(role, role), 'tone': 'gray',
            'members': people, 'count': len(people),
            'active': sum(1 for m in people if m.status == 'active'),
        })
    return sections


def lead_intern_ids() -> set:
    """Кто из людей — тимлид. Тимлиды сотрудники, а не стажёры.

    Используется везде, где считаются или показываются стажёры,
    чтобы тимлиды в эти списки и цифры не попадали.
    """
    return set(
        TeamMember.objects.filter(role=TeamRole.TEAM_LEAD)
        .exclude(intern__isnull=True)
        .values_list('intern_id', flat=True),
    )
