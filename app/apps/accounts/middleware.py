from django.shortcuts import redirect

from apps.accounts.models import User

ALLOWED_PREFIXES = ('/pm/', '/login/', '/logout/', '/static/', '/media/')


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
                return redirect('/')
        return self.get_response(request)
