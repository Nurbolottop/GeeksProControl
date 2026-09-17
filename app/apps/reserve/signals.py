"""Тимлид назначен — он в резерве кадров.

Тимлидом человека делают из разных мест (список тимлидов, команда
проекта, карточка человека, портал тимлида), поэтому следим за самим
сохранением участника команды, а не за каждой из этих страниц.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.teams.models import TeamMember, TeamRole


@receiver(post_save, sender=TeamMember, dispatch_uid='reserve_lead_in_reserve')
def lead_goes_to_reserve(sender, instance, raw=False, **kwargs):
    if raw or instance.role != TeamRole.TEAM_LEAD or not instance.intern_id:
        return
    from apps.reserve.services import ensure_lead_in_reserve

    ensure_lead_in_reserve(instance.intern)
