from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.documents import services as doc_services
from apps.documents.models import (
    CONTRACT,
    FINAL_ACT,
    Document,
    DocumentType,
    REQUIREMENTS,
)
from apps.projects import delivery
from apps.projects.models import Project, ProjectStageKey, ProjectStatus
from apps.projects.services import create_project
from apps.teams.models import TeamMember, TeamRole
from django.contrib.auth import get_user_model

User = get_user_model()


class DeliveryTests(TestCase):
    """Delivery workflow (ТЗ §18): проверка условий и завершение."""

    def setUp(self):
        doc_services.ensure_default_types()
        self.project = Project(
            name='Готовый', progress=100,
            staging_url='https://stage.example.com',
            production_url='https://prod.example.com', domain='example.com',
        )
        create_project(self.project)
        # Закрываем все автоматически созданные задачи чек-листа
        self.project.tasks.update(status='done')
        # Доступы переданы (ТЗ §18)
        self.project.accesses.create(
            service='Админка', login='admin', password='secret',
        )

    def _add_signed_docs(self):
        today = timezone.localdate()
        for code in (CONTRACT, REQUIREMENTS, FINAL_ACT):
            Document.objects.create(
                project=self.project,
                doc_type=DocumentType.objects.get(code=code),
                is_signed=True, signed_date=today, status='signed',
            )

    def test_cannot_complete_without_documents(self):
        success, failed = delivery.complete_project(self.project)
        self.assertFalse(success)
        labels = {check['label'] for check in failed}
        self.assertIn('Договор имеется', labels)
        self.assertIn('Акт подписан', labels)

    def test_complete_when_all_checks_pass(self):
        self._add_signed_docs()
        success, failed = delivery.complete_project(self.project)
        self.assertTrue(success, failed)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, ProjectStatus.COMPLETED)
        self.assertEqual(self.project.current_stage, ProjectStageKey.COMPLETED)
        self.assertIsNotNone(self.project.actual_end_date)

    def test_complete_releases_team(self):
        self._add_signed_docs()
        user = User.objects.create_user(username='dev')
        member = TeamMember.objects.create(
            project=self.project, user=user,
            role=TeamRole.BACKEND, workload=50,
        )
        delivery.complete_project(self.project)
        member.refresh_from_db()
        self.assertEqual(member.status, TeamMember.Status.LEFT)
        self.assertIsNotNone(member.left_at)

    def test_force_complete_requires_reason(self):
        with self.assertRaises(ValueError):
            delivery.complete_project(self.project, force=True, reason='')

    def test_force_complete_writes_history(self):
        success, _ = delivery.complete_project(
            self.project, force=True, reason='Клиент принял без акта',
        )
        self.assertTrue(success)
        record = self.project.history.filter(
            field='Завершение (принудительно)',
        ).first()
        self.assertIsNotNone(record)
        self.assertEqual(record.reason, 'Клиент принял без акта')


class DeliveryOnOverviewTests(TestCase):
    """Завершение проекта живёт во вкладке «Обзор», отдельной «Сдачи» нет."""

    def setUp(self):
        doc_services.ensure_default_types()
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Омур", progress=40))

    def test_overview_shows_completion_block_with_open_checks(self):
        response = self.client.get(self.project.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Завершение проекта")
        self.assertContains(response, "Завершить проект")
        self.assertTrue(response.context["delivery_failed"])
        self.assertFalse(response.context["delivery_ready"])

    def test_delivery_tab_is_gone(self):
        response = self.client.get(self.project.get_absolute_url())
        self.assertNotContains(response, "?tab=delivery")

    def test_complete_returns_to_overview(self):
        response = self.client.post(
            reverse("projects:complete", args=[self.project.pk]),
        )
        self.assertTrue(response.url.endswith("?tab=overview"))
        self.project.refresh_from_db()
        self.assertNotEqual(self.project.status, ProjectStatus.COMPLETED)
