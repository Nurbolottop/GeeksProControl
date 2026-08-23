import datetime

from django.test import TestCase
from django.utils import timezone

from apps.interns.models import Intern, InternStatus
from apps.resources.models import PlannedProject, PlannedProjectNeed
from apps.resources import services
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


class InternsTotalTests(TestCase):
    """Общий итог по стажёрам считается по людям, а не сложением строк."""

    def setUp(self):
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole
        from apps.training.models import Specialization

        self.back = Specialization.objects.create(name="Backend")
        self.project = Project.objects.create(name="Омур")
        busy = Intern.objects.create(full_name="Занятый", specialization=self.back)
        Intern.objects.create(full_name="Свободный", specialization=self.back)
        Intern.objects.create(full_name="Без направления")
        TeamMember.objects.create(
            project=self.project, intern=busy, role=TeamRole.BACKEND,
        )

    def test_total_counts_everyone(self):
        totals = services.interns_total()
        self.assertEqual(totals["total"], 3)
        self.assertEqual(totals["busy"], 1)
        self.assertEqual(totals["free"], 2)
        self.assertEqual(totals["without_spec"], 1)

    def test_total_bigger_than_sum_of_rows_when_spec_missing(self):
        rows_total = sum(row["total"] for row in services.interns_summary())
        self.assertEqual(rows_total, 2)
        self.assertEqual(services.interns_total()["total"], 3)

    def test_page_shows_totals(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        user = get_user_model().objects.create_user(username="head", password="x")
        self.client.force_login(user)
        response = self.client.get(reverse("resources:forecast"))
        self.assertEqual(response.context["totals"]["total"], 3)
        self.assertContains(response, "Всего стажёров")
        self.assertContains(response, "Итого")
