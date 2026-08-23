"""Приводит имена людей к полным ФИО и склеивает дубли.

Короткие имена («Илья», «Артур») превращаются в полные ФИО, а записи,
заведённые дважды на одного человека, сливаются в одну.

    python manage.py fix_names
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.interns.models import Intern
from apps.teams.models import TeamMember

# Короткая запись → полное ФИО
RENAMES = {
    'Мамасаков Артур': 'Артур Мамасаков',
}

# Дубль → к кому присоединить (человек остаётся один)
MERGES = {
    'Артур': 'Артур Мамасаков',
    'Мухаммадали': 'Азамжанов Мухаммадали',
    'Азамжанов Мухамадали': 'Азамжанов Мухаммадали',
    'Айжаз': 'Макамбаева Айжаз',
    'Азимова Каниет': 'Азимова Каниет Медеровна',
    'Камалова Айдеми': 'Камалова Айдеми Майсалбековна',
    'Илья': 'Илья Игольников',
    'Азамат': 'Азамат Талипов',
    'Салиев Яхё': 'Яхебек Салиев',
    'Нурайым': 'Эсенова Нурайым Сапарбековна',
    'Алишер': 'Болотбеков Алишер',
}

# Финальное написание после склейки
FINAL_RENAMES = {}


class Command(BaseCommand):
    help = 'Полные ФИО вместо коротких имён, склейка дублей'

    @transaction.atomic
    def handle(self, *args, **options):
        # --- склейка дублей ---
        for dup_name, target_name in MERGES.items():
            dup = Intern.objects.filter(full_name=dup_name).first()
            target = Intern.objects.filter(full_name=target_name).first()
            if dup is None or target is None or dup.pk == target.pk:
                continue
            moved = 0
            for member in dup.team_memberships.all():
                exists = TeamMember.objects.filter(
                    project=member.project, intern=target,
                ).exists()
                if exists:
                    member.delete()
                else:
                    member.intern = target
                    member.save(update_fields=['intern', 'updated_at'])
                    moved += 1
            dup.delete()
            self.stdout.write(self.style.SUCCESS(
                f'  ~ «{dup_name}» присоединён к «{target_name}» '
                f'(перенесено проектов: {moved})',
            ))

        # --- переименования ---
        for old, new in {**RENAMES, **FINAL_RENAMES}.items():
            person = Intern.objects.filter(full_name=old).first()
            if person is None:
                continue
            if Intern.objects.filter(full_name=new).exclude(pk=person.pk).exists():
                self.stdout.write(self.style.WARNING(
                    f'  ! «{new}» уже есть — «{old}» оставлен как есть',
                ))
                continue
            person.full_name = new
            person.save(update_fields=['full_name', 'updated_at'])
            self.stdout.write(f'  ~ {old} → {new}')

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Людей в базе: {Intern.objects.count()}.',
        ))
