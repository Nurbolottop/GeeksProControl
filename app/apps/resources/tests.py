import datetime

from django.test import TestCase
from django.utils import timezone

from apps.interns.models import Intern, InternStatus
from apps.resources.models import PlannedProject, PlannedProjectNeed
from apps.resources.services import resource_balance
from apps.training.models import Specialization, TrainingGroup


class ResourceBalanceTests(TestCase):
    """Баланс ресурсов (ТЗ §14)."""

    def setUp(self):
        self.backend = Specialization.objects.create(name='Backend')
        self.today = timezone.localdate()

    def _row(self):
        rows = resource_balance(self.today)
        return next(r for r in rows if r['specialization'] == self.backend)

    def test_free_intern_counted_as_available(self):
        Intern.objects.create(
            full_name='A', specialization=self.backend,
            status=InternStatus.ACTIVE,
        )
        row = self._row()
        self.assertEqual(row['available'], 1)
        self.assertEqual(row['balance'], 1)

    def test_graduating_groups_counted(self):
        TrainingGroup.objects.create(
            number='BE-1', specialization=self.backend,
            end_date=self.today + datetime.timedelta(days=30),
            expected_interns=8,
        )
        row = self._row()
        self.assertEqual(row['graduating'], 8)

    def test_planned_projects_create_deficit(self):
        planned = PlannedProject.objects.create(
            name='Big CRM', status=PlannedProject.Status.CONFIRMED,
        )
        PlannedProjectNeed.objects.create(
            planned_project=planned, specialization=self.backend, count=5,
        )
        row = self._row()
        self.assertEqual(row['needed'], 5)
        self.assertEqual(row['balance'], -5)
        self.assertTrue(row['deficit'])

    def test_potential_projects_not_counted(self):
        planned = PlannedProject.objects.create(
            name='Maybe', status=PlannedProject.Status.POTENTIAL,
        )
        PlannedProjectNeed.objects.create(
            planned_project=planned, specialization=self.backend, count=5,
        )
        row = self._row()
        self.assertEqual(row['needed'], 0)
