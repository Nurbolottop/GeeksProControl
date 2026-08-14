from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.projects.models import Project
from apps.teams import services
from apps.teams.forms import TeamMemberForm
from apps.teams.models import TeamMember, TeamRole

User = get_user_model()


class WorkloadTests(TestCase):
    """Загрузка и предупреждение о перегрузе (ТЗ §11)."""

    def setUp(self):
        self.user = User.objects.create_user(username='dev')
        self.project_a = Project.objects.create(name='A')
        self.project_b = Project.objects.create(name='B')

    def test_person_workload_sums_active_memberships(self):
        TeamMember.objects.create(
            project=self.project_a, user=self.user,
            role=TeamRole.BACKEND, workload=60,
        )
        TeamMember.objects.create(
            project=self.project_b, user=self.user,
            role=TeamRole.BACKEND, workload=50,
        )
        self.assertEqual(services.person_workload(user=self.user), 110)

    def test_left_memberships_not_counted(self):
        TeamMember.objects.create(
            project=self.project_a, user=self.user,
            role=TeamRole.BACKEND, workload=90,
            status=TeamMember.Status.LEFT,
        )
        self.assertEqual(services.person_workload(user=self.user), 0)

    def test_workload_bands(self):
        self.assertEqual(services.workload_band(30)[0], 'free')
        self.assertEqual(services.workload_band(70)[0], 'normal')
        self.assertEqual(services.workload_band(95)[0], 'high')
        self.assertEqual(services.workload_band(120)[0], 'overload')

    def test_form_warns_on_overload(self):
        TeamMember.objects.create(
            project=self.project_a, user=self.user,
            role=TeamRole.BACKEND, workload=80,
        )
        form = TeamMemberForm({
            'user': self.user.pk, 'role': TeamRole.BACKEND,
            'workload': 40, 'status': TeamMember.Status.ACTIVE,
        })
        self.assertTrue(form.is_valid(), form.errors)
        warning = form.overload_warning()
        self.assertIsNotNone(warning)
        self.assertIn('120%', warning)

    def test_form_no_warning_under_limit(self):
        form = TeamMemberForm({
            'user': self.user.pk, 'role': TeamRole.BACKEND,
            'workload': 40, 'status': TeamMember.Status.ACTIVE,
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.overload_warning())
