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


class AccessRequestTests(TestCase):
    """Запрос доступов у ПМ и их выдача."""

    def setUp(self):
        from apps.interns.models import Intern
        from apps.teams.models import TeamMember, TeamRole

        self.user = User.objects.create_user(username='dev', password='x')
        self.client.force_login(self.user)
        self.project = make_project(name='Омур')
        create_project(self.project)
        self.pm = Intern.objects.create(full_name='Алтынай Осмонова')
        TeamMember.objects.create(
            project=self.project, intern=self.pm,
            role=TeamRole.PROJECT_MANAGER, workload=50,
        )

    def test_request_goes_to_project_pm_and_notifies(self):
        from apps.notifications.models import Notification
        from apps.projects.models import AccessRequest

        response = self.client.post(
            reverse('projects:access_request_create', args=[self.project.pk]),
            {'service': ['Репозиторий (GitHub/GitLab)', 'База данных'],
             'comment': 'нужно поднять тест'},
        )
        self.assertEqual(response.status_code, 302)
        items = AccessRequest.objects.filter(project=self.project)
        self.assertEqual(items.count(), 2)
        self.assertTrue(all(item.pm == self.pm for item in items))
        self.assertTrue(all(item.is_open for item in items))
        self.assertTrue(
            Notification.objects.filter(title__contains='Запрос доступа').exists(),
        )

    def test_same_open_request_not_duplicated(self):
        from apps.projects.models import AccessRequest

        url = reverse('projects:access_request_create', args=[self.project.pk])
        self.client.post(url, {'service': ['База данных']})
        self.client.post(url, {'service': ['База данных']})
        self.assertEqual(AccessRequest.objects.count(), 1)

    def test_custom_service_is_accepted(self):
        from apps.projects.models import AccessRequest

        self.client.post(
            reverse('projects:access_request_create', args=[self.project.pk]),
            {'custom': 'SMS-шлюз'},
        )
        self.assertTrue(
            AccessRequest.objects.filter(service='SMS-шлюз').exists(),
        )

    def test_provided_request_creates_project_access(self):
        from apps.projects.models import AccessRequest, ProjectAccess

        item = AccessRequest.objects.create(
            project=self.project, service='Репозиторий', pm=self.pm,
        )
        self.client.post(
            reverse('projects:access_request_provide', args=[item.pk]),
            {'url': 'https://github.com/x', 'login': 'dev', 'password': 'secret'},
        )
        item.refresh_from_db()
        self.assertEqual(item.status, AccessRequest.Status.PROVIDED)
        self.assertIsNotNone(item.resolved_at)
        access = ProjectAccess.objects.get(project=self.project)
        self.assertEqual(access.service, 'Репозиторий')
        self.assertEqual(access.login, 'dev')
        self.assertEqual(item.access, access)

    def test_declined_request_keeps_reason(self):
        from apps.projects.models import AccessRequest, ProjectAccess

        item = AccessRequest.objects.create(
            project=self.project, service='Прод-сервер', pm=self.pm,
        )
        self.client.post(
            reverse('projects:access_request_decline', args=[item.pk]),
            {'reason': 'выдам после сдачи'},
        )
        item.refresh_from_db()
        self.assertEqual(item.status, AccessRequest.Status.DECLINED)
        self.assertEqual(item.answer, 'выдам после сдачи')
        self.assertFalse(ProjectAccess.objects.exists())

    def test_access_tab_shows_open_requests(self):
        from apps.projects.models import AccessRequest

        AccessRequest.objects.create(
            project=self.project, service='Домен / DNS', pm=self.pm,
        )
        response = self.client.get(
            f'{self.project.get_absolute_url()}?tab=access',
        )
        self.assertContains(response, 'Домен / DNS')
        self.assertContains(response, 'Алтынай Осмонова')
