from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.interns.models import Intern, InternEvaluation
from apps.interns.services import add_evaluation


class InternRatingTests(TestCase):
    """Средний рейтинг стажёра (ТЗ §12.1)."""

    def test_average_of_single_evaluation(self):
        intern = Intern.objects.create(full_name='Тест Тестов')
        evaluation = InternEvaluation(
            intern=intern, hard_skills=5, quality=4, speed=4,
            responsibility=5, communication=3, teamwork=4, independence=4,
        )
        add_evaluation(evaluation)
        intern.refresh_from_db()
        self.assertEqual(intern.rating, Decimal('4.14'))

    def test_average_over_multiple_evaluations(self):
        intern = Intern.objects.create(full_name='Тест Тестов')
        add_evaluation(InternEvaluation(
            intern=intern, hard_skills=5, quality=5, speed=5,
            responsibility=5, communication=5, teamwork=5, independence=5,
        ))
        add_evaluation(InternEvaluation(
            intern=intern, hard_skills=3, quality=3, speed=3,
            responsibility=3, communication=3, teamwork=3, independence=3,
        ))
        intern.refresh_from_db()
        self.assertEqual(intern.rating, Decimal('4.00'))


class LeadsHiddenFromInternListTests(TestCase):
    """Тимлиды — сотрудники, в списке стажёров их не показываем."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Балажан")
        self.lead = Intern.objects.create(full_name="Болотбеков Алишер")
        self.dev = Intern.objects.create(full_name="Капаров Улар")
        TeamMember.objects.create(
            project=self.project, intern=self.lead, role=TeamRole.TEAM_LEAD,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.dev, role=TeamRole.BACKEND,
        )

    def test_lead_not_in_list(self):
        response = self.client.get(reverse("interns:list"))
        names = [p.full_name for p in response.context["page"].object_list]
        self.assertIn("Капаров Улар", names)
        self.assertNotIn("Болотбеков Алишер", names)

    def test_lead_card_still_opens(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Болотбеков Алишер")

    def test_lead_badge_says_lead(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertEqual(response.context["kind"], "Тимлид направления")


class InternKindBadgeTests(TestCase):
    """ПМ — тоже стажёр, а не отдельная категория (в отличие от тимлида,
    который считается сотрудником): бейдж «Кто в команде» не должен
    превращаться в отдельное «Project Manager», дублируя направление «PM»."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Балажан")
        self.pm = Intern.objects.create(full_name="Болотбекова Умутай")
        TeamMember.objects.create(
            project=self.project, intern=self.pm, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )

    def test_pm_badge_is_intern_not_project_manager(self):
        response = self.client.get(self.pm.get_absolute_url())
        self.assertEqual(response.context["kind"], "Стажёр")
        self.assertNotContains(response, "Project Manager")
