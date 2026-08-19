import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Client
from apps.projects.forms import ProjectForm
from apps.projects.models import (
    DeadlineStatus,
    Project,
    ProjectStageKey,
    ProjectStatus,
    ProjectType,
    lifecycle_stages,
)
from apps.projects.services import calculate_deadline_status, create_project

User = get_user_model()

TODAY = datetime.date(2026, 8, 14)


def make_project(**kwargs) -> Project:
    defaults = {'name': 'Test', 'status': ProjectStatus.ACTIVE, 'progress': 50}
    defaults.update(kwargs)
    return Project(**defaults)


class DeadlineStatusTests(TestCase):
    """Статус срока (ТЗ §8, §22)."""

    def test_completed_project(self):
        project = make_project(status=ProjectStatus.COMPLETED)
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.COMPLETED,
        )

    def test_no_deadline_is_on_track(self):
        project = make_project(planned_end_date=None)
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )

    def test_overdue(self):
        project = make_project(
            planned_end_date=TODAY - datetime.timedelta(days=1),
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.OVERDUE,
        )

    def test_behind_when_deadline_close_and_low_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=2), progress=50,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.BEHIND,
        )

    def test_at_risk_when_week_left_and_low_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=6), progress=50,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.AT_RISK,
        )

    def test_on_track_with_good_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=2), progress=95,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )

    def test_on_track_far_deadline(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=60), progress=5,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )


class CreateProjectTests(TestCase):
    """Набор этапов зависит от типа проекта."""

    def test_web_project_gets_backend_and_frontend(self):
        web_type = ProjectType.objects.create(name='Web-сайт')
        project = make_project(project_type=web_type)
        create_project(project)
        keys = list(project.stages.order_by('order').values_list('key', flat=True))
        self.assertEqual(keys, lifecycle_stages(web_type))
        self.assertIn(ProjectStageKey.BACKEND, keys)
        self.assertIn(ProjectStageKey.FRONTEND, keys)
        self.assertNotIn(ProjectStageKey.MOBILE_DEV, keys)

    def test_mobile_project_gets_mobile_development(self):
        mobile_type = ProjectType.objects.create(name='Mobile App', is_mobile=True)
        project = make_project(project_type=mobile_type)
        create_project(project)
        keys = list(project.stages.values_list('key', flat=True))
        self.assertIn(ProjectStageKey.MOBILE_DEV, keys)
        self.assertNotIn(ProjectStageKey.FRONTEND, keys)

    def test_stage_order_puts_delivery_before_production(self):
        project = make_project()
        create_project(project)
        keys = list(project.stages.order_by('order').values_list('key', flat=True))
        self.assertLess(
            keys.index(ProjectStageKey.DELIVERY),
            keys.index(ProjectStageKey.PRODUCTION),
        )
        self.assertLess(
            keys.index(ProjectStageKey.BACKEND),
            keys.index(ProjectStageKey.STAGING),
        )

    def test_creates_history_and_code(self):
        project = make_project()
        create_project(project)
        self.assertEqual(project.history.count(), 1)
        self.assertTrue(project.code.startswith('GP-'))


class ProjectFormTests(TestCase):
    """Перенос deadline требует причину (ТЗ §21)."""

    def _form_data(self, project, **overrides):
        data = {
            'name': project.name,
            'status': project.status,
            'current_stage': project.current_stage,
            'priority': project.priority,
            'progress': project.progress,
            'planned_end_date': project.planned_end_date,
            'change_reason': '',
        }
        data.update(overrides)
        return data

    def test_deadline_change_requires_reason(self):
        project = make_project(planned_end_date=TODAY)
        create_project(project)
        form = ProjectForm(
            self._form_data(
                project,
                planned_end_date=TODAY + datetime.timedelta(days=10),
            ),
            instance=project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('change_reason', form.errors)

    def test_deadline_change_with_reason_is_valid(self):
        project = make_project(planned_end_date=TODAY)
        create_project(project)
        form = ProjectForm(
            self._form_data(
                project,
                planned_end_date=TODAY + datetime.timedelta(days=10),
                change_reason='Клиент задержал материалы',
            ),
            instance=project,
        )
        self.assertTrue(form.is_valid(), form.errors)


class AuthTests(TestCase):
    """Все внутренние страницы закрыты (ТЗ §2)."""

    def test_anonymous_redirected_to_login(self):
        for url in ['/', '/projects/', '/clients/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/login/'))

    def test_dashboard_opens_for_authenticated_user(self):
        User.objects.create_user(username='head', password='test12345')
        self.client.login(username='head', password='test12345')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Требует внимания')


class ClientProjectsTests(TestCase):
    def test_client_can_have_multiple_projects(self):
        client_obj = Client.objects.create(organization='Org')
        for index in range(2):
            project = make_project(name=f'P{index}', client=client_obj)
            create_project(project)
        self.assertEqual(client_obj.projects.count(), 2)


class ProjectCreationFlowTests(TestCase):
    """Порядок работы: заказчик заводится вместе с проектом, ПМ — в команде."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)

    def test_new_client_created_from_project_form(self):
        response = self.client.post(reverse("projects:create"), {
            "name": "Туризм", "new_client": "ОсОО Туризм",
            "status": "active", "current_stage": "new",
            "priority": "medium", "progress": 0,
        })
        self.assertEqual(response.status_code, 302)
        client_obj = Client.objects.get(organization="ОсОО Туризм")
        project = Project.objects.get(name="Туризм")
        self.assertEqual(project.client, client_obj)
        # После создания сразу зовём назначать команду
        self.assertTrue(response.url.endswith("?tab=team"))

    def test_existing_client_not_duplicated(self):
        Client.objects.create(organization="ОсОО Омур")
        self.client.post(reverse("projects:create"), {
            "name": "Омур", "new_client": "ОсОО Омур",
            "status": "active", "current_stage": "new",
            "priority": "medium", "progress": 0,
        })
        self.assertEqual(Client.objects.filter(organization="ОсОО Омур").count(), 1)

    def test_pm_and_leads_come_from_team(self):
        from apps.interns.models import Intern
        from apps.teams.models import TeamMember, TeamRole

        project = make_project(name="Омур")
        create_project(project)
        self.assertIsNone(project.pm)
        self.assertEqual(project.leads, [])

        pm = Intern.objects.create(full_name="Алтынай")
        lead = Intern.objects.create(full_name="Бексултан")
        TeamMember.objects.create(
            project=project, intern=pm, role=TeamRole.PROJECT_MANAGER, workload=50,
        )
        TeamMember.objects.create(
            project=project, intern=lead, role=TeamRole.TEAM_LEAD, workload=50,
        )
        project.refresh_from_db()
        self.assertEqual(project.pm, pm)
        self.assertEqual(project.leads, [lead])
        self.assertTrue(project.has_pm)

    def test_projects_without_pm_selector(self):
        from apps.projects import selectors

        project = make_project(name="Без ПМ")
        create_project(project)
        self.assertIn(project, selectors.projects_without_pm())

    def test_group_created_together_with_project(self):
        from apps.flows.models import Flow, Group

        Flow.objects.create(number=1, status=Flow.Status.ACTIVE)
        project = make_project(name="Новый")
        create_project(project)
        group = Group.objects.get(project=project)
        self.assertEqual(group.flow.number, 1)
        project.refresh_from_db()
        self.assertEqual(project.flow, group.flow)
        self.assertEqual(project.number_in_flow, group.number)

    def test_flow_created_when_none_exists(self):
        from apps.flows.models import Flow

        self.assertFalse(Flow.objects.exists())
        project = make_project(name="Первый")
        create_project(project)
        self.assertEqual(Flow.objects.count(), 1)
        self.assertIsNotNone(project.group)

    def test_groups_numbered_sequentially(self):
        first = make_project(name="Раз")
        create_project(first)
        second = make_project(name="Два")
        create_project(second)
        self.assertEqual(first.group.number, 1)
        self.assertEqual(second.group.number, 2)

    def test_create_form_has_no_links_and_dates(self):
        from apps.projects.forms import ProjectCreateForm

        fields = set(ProjectCreateForm().fields)
        self.assertEqual(
            fields, {"name", "client", "city", "project_type", "description"},
        )
