from apps.notifications import services


def notifications(request):
    """Счётчик непрочитанных уведомлений в навигации."""
    if not request.user.is_authenticated:
        return {}
    return {'unread_notifications': services.unread_count()}
