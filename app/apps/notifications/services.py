"""NotificationService (ТЗ §46.1)."""
from apps.notifications.models import Notification, NotificationLevel


def notify(
    title: str, *, level: str = NotificationLevel.INFO,
    description: str = '', url: str = '', dedup_key: str = '',
) -> Notification | None:
    """Создаёт уведомление. С dedup_key не дублирует незакрытые."""
    if dedup_key and Notification.objects.filter(
        dedup_key=dedup_key, is_closed=False,
    ).exists():
        return None
    return Notification.objects.create(
        title=title, level=level, description=description,
        url=url, dedup_key=dedup_key,
    )


def unread_count() -> int:
    return Notification.objects.filter(is_read=False, is_closed=False).count()
