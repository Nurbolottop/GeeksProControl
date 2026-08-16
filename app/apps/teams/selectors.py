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


def group_by_role(members) -> list[dict]:
    """Разбивает состав команды на секции по направлениям.

    Возвращает только непустые направления, в порядке ROLE_ORDER.
    """
    buckets: dict[str, list[TeamMember]] = {}
    for member in members:
        buckets.setdefault(member.role, []).append(member)

    sections = []
    for role in ROLE_ORDER:
        people = buckets.pop(role, [])
        if people:
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
