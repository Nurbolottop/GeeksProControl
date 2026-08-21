from django.test import TestCase
from django.urls import reverse

from apps.projects.models import Project, ProjectStageKey
from apps.projects.services import create_project, move_project_to_stage
from apps.tasks.models import Task, TaskStatus, TaskTemplate
from apps.tasks.services import DEFAULT_TEMPLATES, generate_checklist, set_task_status


class ChecklistTests(TestCase):
    """Задачи заводятся руками — автоматических чек-листов больше нет."""

    def test_new_project_has_no_tasks(self):
        project = Project(name='Test')
        create_project(project)
        self.assertEqual(project.tasks.count(), 0)

    def test_move_to_delivery_does_not_create_tasks(self):
        project = Project(name='Test')
        create_project(project)
        move_project_to_stage(project, ProjectStageKey.DELIVERY)
        self.assertEqual(project.tasks.count(), 0)

    def test_checklist_can_still_be_generated_manually(self):
        project = Project(name='Test')
        create_project(project)
        generate_checklist(project, TaskTemplate.Kind.PROJECT_NEW)
        expected = DEFAULT_TEMPLATES[TaskTemplate.Kind.PROJECT_NEW]
        titles = set(project.tasks.values_list('title', flat=True))
        self.assertTrue(set(expected).issubset(titles))

    def test_manual_checklist_not_duplicated(self):
        project = Project(name='Test')
        create_project(project)
        generate_checklist(project, TaskTemplate.Kind.PROJECT_NEW)
        count_before = project.tasks.count()
        generate_checklist(project, TaskTemplate.Kind.PROJECT_NEW)
        self.assertEqual(project.tasks.count(), count_before)


class TaskStatusTests(TestCase):
    def test_done_sets_completed_date(self):
        task = Task.objects.create(title='T')
        set_task_status(task, TaskStatus.DONE)
        self.assertIsNotNone(task.completed_at)

    def test_reopen_clears_completed_date(self):
        task = Task.objects.create(title='T')
        set_task_status(task, TaskStatus.DONE)
        set_task_status(task, TaskStatus.IN_PROGRESS)
        self.assertIsNone(task.completed_at)


class TaskEditDeleteTests(TestCase):
    """Задачу можно отредактировать и удалить из карточки проекта."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.projects.services import create_project

        self.user = get_user_model().objects.create_user(username="pm", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="ОБА"))
        self.task = Task.objects.create(
            project=self.project, title="Устроить созвон с тимлид",
        )

    def test_row_has_edit_and_delete(self):
        response = self.client.get(f"{self.project.get_absolute_url()}?tab=tasks")
        self.assertContains(response, reverse("tasks:update", args=[self.task.pk]))
        self.assertContains(response, reverse("tasks:delete", args=[self.task.pk]))

    def test_delete_removes_task_and_returns_to_project(self):
        response = self.client.post(reverse("tasks:delete", args=[self.task.pk]))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertTrue(response.url.endswith("?tab=tasks"))

    def test_get_does_not_delete(self):
        self.client.get(reverse("tasks:delete", args=[self.task.pk]))
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_edit_saves_new_title(self):
        self.client.post(reverse("tasks:update", args=[self.task.pk]), {
            "title": "Созвон с тимлидом", "project": self.project.pk,
            "priority": "medium", "status": "new",
        })
        self.task.refresh_from_db()
        self.assertEqual(self.task.title, "Созвон с тимлидом")
