"""Очищает ежедневные пункты проектов вместе с отметками.

    python manage.py reset_project_daily
"""
from django.core.management.base import BaseCommand

from apps.dailycheck.models import ProjectCheckItem, ProjectCheckMark


class Command(BaseCommand):
    help = 'Удаляет все ежедневные пункты проектов и отметки по ним'

    def handle(self, *args, **options):
        marks = ProjectCheckMark.objects.count()
        items = ProjectCheckItem.objects.count()
        ProjectCheckItem.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(
            f'Удалено пунктов: {items}, отметок: {marks}.',
        ))
