import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


class ProjectDailyTests(TestCase):
    """Ежедневная проверка внутри проекта."""

    def setUp(self):
        from apps.projects.models import Project
        from apps.projects.services import create_project

        self.user = User.objects.create_user(username="pm", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Туризм"))
        self.today = timezone.localdate()

    def test_tab_opens_with_empty_list(self):
        from apps.dailycheck.models import ProjectCheckItem

        response = self.client.get(f"{self.project.get_absolute_url()}?tab=daily")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ProjectCheckItem.objects.filter(project=self.project).exists(),
        )
        self.assertContains(response, "добавьте свои")

    def test_toggle_and_untoggle(self):
        from apps.dailycheck.models import ProjectCheckItem, ProjectCheckMark

        item = ProjectCheckItem.objects.create(
            project=self.project, title="Свой пункт")
        url = reverse("dailycheck:project_toggle", args=[item.pk])
        self.client.post(url, {"date": self.today.isoformat()})
        self.assertTrue(ProjectCheckMark.objects.filter(item=item).exists())
        self.client.post(url, {"date": self.today.isoformat()})
        self.assertFalse(ProjectCheckMark.objects.filter(item=item).exists())

    def test_item_removed_only_from_this_project(self):
        from apps.dailycheck.models import ProjectCheckItem
        from apps.projects.models import Project
        from apps.projects.services import create_project

        other = create_project(Project(name="Учкун"))
        item = ProjectCheckItem.objects.create(
            project=self.project, title="Общий пункт")
        ProjectCheckItem.objects.create(project=other, title="Общий пункт")
        self.client.post(reverse("dailycheck:project_item_delete", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.assertTrue(ProjectCheckItem.objects.filter(
            project=other, title=item.title, is_active=True).exists())

    def test_custom_item_added_to_project(self):
        from apps.dailycheck.models import ProjectCheckItem

        self.client.post(
            reverse("dailycheck:project_item_create", args=[self.project.pk]),
            {"title": "Очередь заявок пустая"},
        )
        self.assertTrue(ProjectCheckItem.objects.filter(
            project=self.project, title="Очередь заявок пустая").exists())

    def test_tab_badge_counts_unchecked(self):
        from apps.dailycheck.models import ProjectCheckItem

        item = ProjectCheckItem.objects.create(
            project=self.project, title="Раз")
        ProjectCheckItem.objects.create(project=self.project, title="Два")
        total = ProjectCheckItem.objects.filter(project=self.project).count()
        self.client.post(
            reverse("dailycheck:project_toggle", args=[item.pk]),
            {"date": self.today.isoformat()},
        )
        response = self.client.get(self.project.get_absolute_url())
        self.assertEqual(response.context["daily_left"], total - 1)
