from apps.training import selectors


def academy_nav(request):
    """Дерево «филиал → направление» для сайдбара IT-академии."""
    if not request.user.is_authenticated:
        return {}
    return {'academy_nav': selectors.nav_tree()}
