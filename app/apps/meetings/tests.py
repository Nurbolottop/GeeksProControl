import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.meetings.models import Meeting, MeetingDecision
from apps.meetings.services import build_auto_agenda, create_task_from_decision
from apps.projects.models import Project

User = get_user_model()


class MeetingDecisionTests(TestCase):
    """Решения собраний → задачи (ТЗ §19.2)."""

    def setUp(self):
        self.project = Project.objects.create(name='P')
        self.meeting = Meeting.objects.create(
            topic='Weekly', date=timezone.localdate(), project=self.project,
        )
        self.user = User.objects.create_user(username='head')

    def test_create_task_from_decision(self):
        decision = MeetingDecision.objects.create(
            meeting=self.meeting, text='Починить деплой',
            responsible=self.user,
            deadline=timezone.localdate() + datetime.timedelta(days=3),
        )
        task = create_task_from_decision(decision, user=self.user)
        self.assertEqual(task.title, 'Починить деплой')
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.assignee, self.user)
        decision.refresh_from_db()
        self.assertEqual(decision.task, task)

    def test_create_task_is_idempotent(self):
        decision = MeetingDecision.objects.create(
            meeting=self.meeting, text='Решение',
        )
        task1 = create_task_from_decision(decision)
        task2 = create_task_from_decision(decision)
        self.assertEqual(task1, task2)


class AutoAgendaTests(TestCase):
    """Автоматическая повестка (ТЗ §19.1)."""

    def test_overdue_project_appears_in_agenda(self):
        Project.objects.create(
            name='Просроченный',
            planned_end_date=timezone.localdate() - datetime.timedelta(days=5),
        )
        agenda = build_auto_agenda()
        self.assertTrue(
            any('Просроченный' in point for point in agenda),
            agenda,
        )
