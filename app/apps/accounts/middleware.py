from django.shortcuts import redirect

from apps.accounts.models import User

ALLOWED_PREFIXES = ('/pm/', '/login/', '/logout/', '/static/', '/media/')
LEAD_ALLOWED_PREFIXES = ('/lead/', '/login/', '/logout/', '/static/', '/media/')


class PMScopeMiddleware:
    """Двусторонняя граница между обычным сайтом и порталом ПМ.

    ПМ видит только /pm/ — ни общий сайдбар, ни чужие проекты. И наоборот:
    /pm/ — только для ПМ, остальным (head/administrator) там делать
    нечего, их уводит на обычный дашборд.

    Один choke point вместо декоратора на каждый view: система устроена
    так, что новые/старые страницы автоматически закрыты для ПМ по
    умолчанию, если явно не в allowlist.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            is_pm = user.role == User.Role.PROJECT_MANAGER
            if is_pm and not request.path.startswith(ALLOWED_PREFIXES):
                return redirect('pm_portal:dashboard')
            if not is_pm and request.path.startswith('/pm/'):
                # Тимлида уводим сразу в его портал, а не на общий
                # сайт — иначе LeadScopeMiddleware следующим запросом
                # тут же отправит его обратно и получится зацикливание.
                if user.role == User.Role.TEAM_LEAD:
                    return redirect('lead_portal:dashboard')
                return redirect('/')
        return self.get_response(request)


class LeadScopeMiddleware:
    """Та же граница, что и у ПМ (см. PMScopeMiddleware), но для
    тимлидов и портала /lead/ — независимо друг от друга, роль у
    пользователя ровно одна."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            is_lead = user.role == User.Role.TEAM_LEAD
            if is_lead and not request.path.startswith(LEAD_ALLOWED_PREFIXES):
                return redirect('lead_portal:dashboard')
            if not is_lead and request.path.startswith('/lead/'):
                # Симметрично PMScopeMiddleware — ПМ уводим в его
                # портал напрямую, без зацикливания через общий сайт.
                if user.role == User.Role.PROJECT_MANAGER:
                    return redirect('pm_portal:dashboard')
                return redirect('/')
        return self.get_response(request)
