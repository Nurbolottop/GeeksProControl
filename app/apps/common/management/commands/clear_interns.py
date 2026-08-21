"""Очищает список стажёров, оставляя ПМ и тимлидов.

Кого оставляем: всех, у кого есть роль PM или «Тимлид» хотя бы в одной
команде. Остальных — удаляем вместе с их участием в проектах.

    python manage.py clear_interns --dry-run   # только показать
    python manage.py clear_interns             # удалить
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern
from apps.teams.models import TeamMember, TeamRole

KEEP_ROLES = [TeamRole.PROJECT_MANAGER, TeamRole.TEAM_LEAD]


class Command(BaseCommand):
    help = 'Удаляет стажёров, кроме ПМ и тимлидов'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='показать, кого удалит, но ничего не менять',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        keep_ids = set(
            TeamMember.objects.filter(role__in=KEEP_ROLES)
            .exclude(intern__isnull=True)
            .values_list('intern_id', flat=True),
        )
        keep = Intern.objects.filter(pk__in=keep_ids).order_by('full_name')
        drop = Intern.objects.exclude(pk__in=keep_ids).order_by('full_name')

        self.stdout.write(self.style.SUCCESS(f'Остаются ({keep.count()}):'))
        for intern in keep:
            roles = ', '.join(sorted({
                member.get_role_display()
                for member in intern.team_memberships.filter(role__in=KEEP_ROLES)
            }))
            self.stdout.write(f'  = {intern.full_name} — {roles}')

        count = drop.count()
        self.stdout.write(f'Удаляются: {count}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Пробный запуск — ничего не удалено.'))
            return

        drop.delete()
        self.stdout.write(self.style.SUCCESS(
            f'Удалено стажёров: {count}. Осталось: {Intern.objects.count()}.',
        ))
