from django.shortcuts import redirect

from apps.accounts.models import User

ALLOWED_PREFIXES = ('/pm/', '/login/', '/logout/', '/static/', '/media/')


class PMScopeMiddleware:
    """ПМ видит только свой портал (/pm/) — ни общий сайдбар, ни чужие проекты.

    Один choke point вместо декоратора на каждый view: система устроена
    так, что новые/старые страницы автоматически закрыты для ПМ по
    умолчанию, если явно не в allowlist.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and user.role == User.Role.PROJECT_MANAGER
            and not request.path.startswith(ALLOWED_PREFIXES)
        ):
            return redirect('pm_portal:dashboard')
        return self.get_response(request)
