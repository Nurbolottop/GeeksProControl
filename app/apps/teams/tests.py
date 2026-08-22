from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams import services
from apps.teams.forms import TeamMemberForm
from apps.teams.models import TeamMember, TeamRole

User = get_user_model()


class WorkloadTests(TestCase):
    """Загрузка и предупреждение о перегрузе (ТЗ §11)."""

    def setUp(self):
        self.user = User.objects.create_user(username='dev')
        self.person = Intern.objects.create(full_name='Курманбеков Эрбол')
        self.project_a = Project.objects.create(name='A')
        self.project_b = Project.objects.create(name='B')

    def test_person_workload_sums_active_memberships(self):
        TeamMember.objects.create(
            project=self.project_a, intern=self.person,
            role=TeamRole.BACKEND, workload=60,
        )
        TeamMember.objects.create(
            project=self.project_b, intern=self.person,
            role=TeamRole.BACKEND, workload=50,
        )
        self.assertEqual(services.person_workload(intern=self.person), 110)

    def test_left_memberships_not_counted(self):
        TeamMember.objects.create(
            project=self.project_a, intern=self.person,
            role=TeamRole.BACKEND, workload=90,
            status=TeamMember.Status.LEFT,
        )
        self.assertEqual(services.person_workload(intern=self.person), 0)

    def test_workload_bands(self):
        self.assertEqual(services.workload_band(30)[0], 'free')
        self.assertEqual(services.workload_band(70)[0], 'normal')
        self.assertEqual(services.workload_band(95)[0], 'high')
        self.assertEqual(services.workload_band(120)[0], 'overload')

    def test_form_warns_when_person_on_many_projects(self):
        for project in (self.project_a, self.project_b):
            TeamMember.objects.create(
                project=project, intern=self.person, role=TeamRole.BACKEND,
            )
        form = TeamMemberForm({'intern': self.person.pk})
        self.assertTrue(form.is_valid(), form.errors)
        warning = form.overload_warning()
        self.assertIsNotNone(warning)
        self.assertIn('2 проектах', warning)

    def test_form_no_warning_for_first_project(self):
        form = TeamMemberForm({'intern': self.person.pk})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.overload_warning())

    def test_member_requires_person(self):
        form = TeamMemberForm({
            'role': TeamRole.BACKEND, 'workload': 40,
            'status': TeamMember.Status.ACTIVE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('intern', form.errors)


class AddNewPersonTests(TestCase):
    """Человека, которого нет в базе, можно завести прямо из формы команды."""

    def setUp(self):
        from apps.projects.services import create_project
        from apps.training.models import Specialization

        self.user = User.objects.create_user(username="pm", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Омур"))
        self.spec = Specialization.objects.create(name="Backend")

    def test_new_person_created_and_added_to_team(self):
        response = self.client.post(
            reverse("teams:member_add", args=[self.project.pk]),
            {"new_person": "Асанов Азамат", "new_spec": self.spec.pk,
             "workload": 50},
        )
        self.assertEqual(response.status_code, 302)
        intern = Intern.objects.get(full_name="Асанов Азамат")
        self.assertEqual(intern.specialization, self.spec)
        self.assertTrue(
            TeamMember.objects.filter(project=self.project, intern=intern).exists(),
        )

    def test_existing_person_not_duplicated(self):
        Intern.objects.create(full_name="Асанов Азамат")
        self.client.post(
            reverse("teams:member_add", args=[self.project.pk]),
            {"new_person": "Асанов Азамат", "workload": 50},
        )
        self.assertEqual(Intern.objects.filter(full_name="Асанов Азамат").count(), 1)

    def test_form_page_lists_specializations(self):
        response = self.client.get(
            reverse("teams:member_add", args=[self.project.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backend")
        self.assertContains(response, "new_person")


class RoleSectionAddTests(TestCase):
    """В каждое направление добавляют отдельно, список фильтруется."""

    def setUp(self):
        from apps.projects.services import create_project
        from apps.training.models import Specialization

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Балажан"))
        self.pm_spec = Specialization.objects.create(name="PM")
        self.back_spec = Specialization.objects.create(name="Backend")
        self.pm = Intern.objects.create(full_name="Айдана", specialization=self.pm_spec)
        self.dev = Intern.objects.create(full_name="Капаров Улар", specialization=self.back_spec)

    def _url(self, role):
        return f"{reverse(teams:member_add, args=[self.project.pk])}?role={role}"

    def test_pm_section_lists_only_pms(self):
        response = self.client.get(self._url("pm"))
        self.assertEqual(response.status_code, 200)
        people = [p["name"] for p in response.context["people"]]
        self.assertIn("Айдана", people)
        self.assertNotIn("Капаров Улар", people)

    def test_backend_section_lists_only_backend(self):
        response = self.client.get(self._url("backend"))
        people = [p["name"] for p in response.context["people"]]
        self.assertEqual(people, ["Капаров Улар"])

    def test_role_applied_on_save(self):
        self.client.post(self._url("pm"), {"intern": self.pm.pk, "role": "pm"})
        member = TeamMember.objects.get(project=self.project, intern=self.pm)
        self.assertEqual(member.role, TeamRole.PROJECT_MANAGER)

    def test_team_lead_section_sets_lead_role(self):
        self.client.post(
            self._url("team_lead"),
            {"intern": self.dev.pk, "role": "team_lead"},
        )
        member = TeamMember.objects.get(project=self.project, intern=self.dev)
        self.assertEqual(member.role, TeamRole.TEAM_LEAD)

    def test_empty_sections_shown_on_team_tab(self):
        response = self.client.get(f"{self.project.get_absolute_url()}?tab=team")
        roles = [s["role"] for s in response.context["team_sections"]]
        for role in ("pm", "team_lead", "uxui", "backend", "frontend", "qa"):
            self.assertIn(role, roles)
