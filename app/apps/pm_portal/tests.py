from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole

Model = get_user_model()


class PmProjectOwnershipTests(TestCase):
    """ПМ видит только тот проект, где сам активный TeamMember(role='pm')."""

    def setUp(self):
        self.pm_user = Model.objects.create_user(
            username="+996700000010", password="x", role=User.Role.PROJECT_MANAGER,
        )
        self.pm_intern = Intern.objects.create(
            full_name="Тестов ПМ", user=self.pm_user,
        )
        self.project_a = Project.objects.create(name="Проект A")
        self.project_b = Project.objects.create(name="Проект B")
        TeamMember.objects.create(
            project=self.project_a, intern=self.pm_intern, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.force_login(self.pm_user)

    def test_dashboard_lists_only_own_project(self):
        response = self.client.get(reverse("pm_portal:dashboard"))
        names = [p.name for p in response.context["projects"]]
        self.assertEqual(names, ["Проект A"])

    def test_can_open_own_project(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Проект A")

    def test_cannot_open_foreign_project(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_left_membership_does_not_grant_access(self):
        TeamMember.objects.create(
            project=self.project_b, intern=self.pm_intern, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.LEFT,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_non_pm_role_on_project_does_not_grant_access(self):
        """Например, тимлид или бэкендер на проекте — не ПМ, доступа нет."""
        TeamMember.objects.create(
            project=self.project_b, intern=self.pm_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)


class PmReportTests(PmProjectOwnershipTests):
    """Отчёты — доступны только на своём проекте."""

    def test_can_create_report_on_own_project(self):
        from apps.projects.models import ProjectReport

        self.client.post(
            reverse("pm_portal:report_create", args=[self.project_a.pk]),
            {"text": "Сделали бэкенд, начали фронт."},
        )
        report = ProjectReport.objects.get(project=self.project_a)
        self.assertEqual(report.author, self.pm_user)

    def test_cannot_create_report_on_foreign_project(self):
        from apps.projects.models import ProjectReport

        response = self.client.post(
            reverse("pm_portal:report_create", args=[self.project_b.pk]),
            {"text": "Не мой проект."},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectReport.objects.filter(project=self.project_b).exists())

    def test_cannot_edit_report_by_guessing_id_from_other_project(self):
        from apps.projects.models import ProjectReport

        foreign_report = ProjectReport.objects.create(
            project=self.project_b, text="Чужой отчёт",
        )
        response = self.client.post(
            reverse(
                "pm_portal:report_update",
                args=[self.project_a.pk, foreign_report.pk],
            ),
            {"text": "Подмена"},
        )
        self.assertEqual(response.status_code, 404)
        foreign_report.refresh_from_db()
        self.assertEqual(foreign_report.text, "Чужой отчёт")
