from django.test import TestCase

from apps.projects.models import Project, ProjectStageKey
from apps.projects.services import create_project, move_project_to_stage
from apps.tasks.models import Task, TaskStatus, TaskTemplate
from apps.tasks.services import DEFAULT_TEMPLATES, generate_checklist, set_task_status


class ChecklistTests(TestCase):
    """Автоматические чек-листы задач (ТЗ §10.1)."""

    def test_new_project_gets_default_checklist(self):
        project = Project(name='Test')
        create_project(project)
        expected = DEFAULT_TEMPLATES[TaskTemplate.Kind.PROJECT_NEW]
        titles = set(project.tasks.values_list('title', flat=True))
        self.assertTrue(set(expected).issubset(titles))

    def test_move_to_delivery_creates_delivery_checklist(self):
        project = Project(name='Test')
        create_project(project)
        move_project_to_stage(project, ProjectStageKey.DELIVERY)
        titles = set(project.tasks.values_list('title', flat=True))
        for expected_title in DEFAULT_TEMPLATES[TaskTemplate.Kind.DELIVERY]:
            self.assertIn(expected_title, titles)

    def test_checklist_not_duplicated(self):
        project = Project(name='Test')
        create_project(project)
        count_before = project.tasks.count()
        generate_checklist(project, TaskTemplate.Kind.PROJECT_NEW)
        self.assertEqual(project.tasks.count(), count_before)

    def test_custom_templates_override_defaults(self):
        TaskTemplate.objects.create(
            kind=TaskTemplate.Kind.PROJECT_NEW, title='Своя задача', order=1,
        )
        project = Project(name='Test')
        create_project(project)
        titles = list(project.tasks.values_list('title', flat=True))
        self.assertEqual(titles, ['Своя задача'])


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
