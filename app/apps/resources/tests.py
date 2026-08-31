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


class LeadsNotCountedAsInternsTests(TestCase):
    """Тимлид — сотрудник: ни в направлениях, ни в общем счёте его нет."""

    def setUp(self):
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole
        from apps.training.models import Specialization

        self.spec = Specialization.objects.create(name="Backend")
        project = Project.objects.create(name="Омур")
        self.dev = Intern.objects.create(
            full_name="Стажёр", specialization=self.spec,
            status=InternStatus.ACTIVE,
        )
        self.lead = Intern.objects.create(
            full_name="Тимлид", specialization=self.spec,
            status=InternStatus.ACTIVE,
        )
        TeamMember.objects.create(
            project=project, intern=self.dev, role=TeamRole.BACKEND,
        )
        TeamMember.objects.create(
            project=project, intern=self.lead, role=TeamRole.TEAM_LEAD,
        )

    def test_direction_row_without_lead(self):
        row = next(
            r for r in services.interns_summary()
            if r["specialization"] == self.spec
        )
        self.assertEqual(row["total"], 1)
        self.assertEqual(row["busy"], 1)

    def test_totals_without_lead(self):
        totals = services.interns_total()
        self.assertEqual(totals["total"], 1)
        self.assertEqual(totals["leads"], 1)

    def test_weekly_report_counts_interns_without_leads(self):
        import datetime
        from apps.reports import weekly_form

        data = weekly_form.build(datetime.date(2026, 8, 17))
        self.assertEqual(data["interns"]["active"], 1)


class StaffingRequestTests(TestCase):
    """Запрос на стажёров: сколько нужно, на какой проект, к какой дате."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project

        self.spec = Specialization.objects.create(name="Backend")
        self.project = Project.objects.create(name="Балажан")
        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)

    def test_create_request(self):
        from django.urls import reverse

        response = self.client.post(reverse("resources:staffing_requests"), {
            "project": self.project.pk, "specialization": self.spec.pk,
            "count": 2, "needed_by": "2026-09-15", "comment": "Срочно",
        })
        self.assertEqual(response.status_code, 302)
        from apps.resources.models import StaffingRequest

        req = StaffingRequest.objects.get()
        self.assertEqual(req.project, self.project)
        self.assertEqual(req.count, 2)
        self.assertEqual(req.created_by, self.user)
        self.assertFalse(req.is_closed)

    def test_open_requests_shown_on_page(self):
        from django.urls import reverse
        from apps.resources.models import StaffingRequest

        StaffingRequest.objects.create(
            project=self.project, specialization=self.spec, count=3,
        )
        response = self.client.get(reverse("resources:staffing_requests"))
        self.assertContains(response, "Балажан")
        self.assertEqual(len(response.context["open_requests"]), 1)

    def test_toggle_closes_and_reopens(self):
        from django.urls import reverse
        from apps.resources.models import StaffingRequest

        req = StaffingRequest.objects.create(
            project=self.project, specialization=self.spec, count=1,
        )
        self.client.post(reverse("resources:staffing_request_toggle", args=[req.pk]))
        req.refresh_from_db()
        self.assertTrue(req.is_closed)

        self.client.post(reverse("resources:staffing_request_toggle", args=[req.pk]))
        req.refresh_from_db()
        self.assertFalse(req.is_closed)

    def test_delete_removes_request(self):
        from django.urls import reverse
        from apps.resources.models import StaffingRequest

        req = StaffingRequest.objects.create(
            project=self.project, specialization=self.spec, count=1,
        )
        self.client.post(reverse("resources:staffing_request_delete", args=[req.pk]))
        self.assertFalse(StaffingRequest.objects.filter(pk=req.pk).exists())

    def test_archived_project_not_selectable(self):
        from apps.projects.models import Project

        archived = Project.objects.create(name="Старый", is_archived=True)
        from apps.resources.views import StaffingRequestForm

        form = StaffingRequestForm()
        self.assertNotIn(archived, form.fields["project"].queryset)
