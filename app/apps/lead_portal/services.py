from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole


def lead_project_or_404(user, project_pk) -> Project:
    """Единственная точка проверки: проект, где user — активный тимлид.

    Логин тимлида, как и у ПМ, лежит в intern.user — сам тимлид на
    проекте это TeamMember с role='team_lead', привязанный через intern.
    """
    return get_object_or_404(
        Project,
        pk=project_pk,
        team_members__intern__user=user,
        team_members__role=TeamRole.TEAM_LEAD,
        team_members__status=TeamMember.Status.ACTIVE,
    )


def lead_projects(user):
    """Проекты, где user — активный тимлид (для дашборда)."""
    return Project.objects.filter(
        team_members__intern__user=user,
        team_members__role=TeamRole.TEAM_LEAD,
        team_members__status=TeamMember.Status.ACTIVE,
    ).distinct()


def lead_own_role(user):
    """Направление тимлида по его собственной специализации (Backend,
    Frontend...) — именно этих стажёров команды он видит и добавляет,
    остальные направления и ПМ в его портале не показываются."""
    from apps.teams.forms import ROLE_BY_SPECIALIZATION

    intern = getattr(user, 'intern_profile', None)
    spec = getattr(intern, 'specialization', None) if intern else None
    return ROLE_BY_SPECIALIZATION.get(spec.name) if spec else None
