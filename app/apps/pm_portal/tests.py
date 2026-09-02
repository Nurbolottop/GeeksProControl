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
