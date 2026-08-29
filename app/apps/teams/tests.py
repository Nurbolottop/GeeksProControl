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
        base = reverse("teams:member_add", args=[self.project.pk])
        return f"{base}?role={role}"

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

    def test_team_lead_section_lists_only_existing_leads(self):
        """Тут добавляют существующего тимлида ещё на один проект — не
        повышают случайного стажёра. Первого тимлида направления заводят
        через страницу «Тимлиды» (там есть «+ новый человек»)."""
        from apps.projects.services import create_project

        other_project = create_project(Project(name="Учкун"))
        TeamMember.objects.create(
            project=other_project, intern=self.dev, role=TeamRole.TEAM_LEAD,
        )
        response = self.client.get(self._url("team_lead"))
        people = [p["name"] for p in response.context["people"]]
        self.assertIn("Капаров Улар", people)
        self.assertNotIn("Айдана", people)

    def test_team_lead_section_rejects_intern_who_is_not_a_lead(self):
        response = self.client.post(
            self._url("team_lead"),
            {"intern": self.dev.pk, "role": "team_lead"},
        )
        self.assertFalse(
            TeamMember.objects.filter(project=self.project, intern=self.dev).exists(),
        )

    def test_team_lead_section_accepts_existing_lead(self):
        from apps.projects.services import create_project

        other_project = create_project(Project(name="Учкун"))
        TeamMember.objects.create(
            project=other_project, intern=self.dev, role=TeamRole.TEAM_LEAD,
        )
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


class LeadSectionTests(TestCase):
    """Раздел «Тимлиды»: назначить, снять, посмотреть по проектам."""

    def setUp(self):
        from apps.projects.services import create_project
        from apps.training.models import Specialization

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Балажан"))
        self.spec = Specialization.objects.create(name="Backend")
        self.person = Intern.objects.create(
            full_name="Болотбеков Алишер", specialization=self.spec,
        )

    def test_page_lists_leads(self):
        TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.TEAM_LEAD,
        )
        response = self.client.get(reverse("teams:lead_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Болотбеков Алишер")
        self.assertEqual(response.context["total"], 1)

    def test_assign_lead(self):
        self.client.post(reverse("teams:lead_add"), {
            "intern": self.person.pk, "project": self.project.pk,
        })
        member = TeamMember.objects.get(project=self.project, intern=self.person)
        self.assertEqual(member.role, TeamRole.TEAM_LEAD)

    def test_existing_member_becomes_lead(self):
        member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.BACKEND,
        )
        self.client.post(reverse("teams:lead_add"), {
            "intern": self.person.pk, "project": self.project.pk,
        })
        member.refresh_from_db()
        self.assertEqual(member.role, TeamRole.TEAM_LEAD)

    def test_remove_lead_keeps_person(self):
        member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.TEAM_LEAD,
        )
        self.client.post(reverse("teams:lead_remove", args=[member.pk]))
        self.assertFalse(TeamMember.objects.filter(pk=member.pk).exists())
        self.assertTrue(Intern.objects.filter(pk=self.person.pk).exists())

    def test_new_person_can_be_assigned_lead(self):
        self.client.post(reverse("teams:lead_add"), {
            "new_person": "Саидахмат Каримов", "project": self.project.pk,
        })
        intern = Intern.objects.get(full_name="Саидахмат Каримов")
        member = TeamMember.objects.get(intern=intern)
        self.assertEqual(member.role, TeamRole.TEAM_LEAD)

    def test_assign_lead_returns_to_given_next_url(self):
        """Со страницы стажёра — назад на страницу стажёра, а не в общий
        список тимлидов, чтобы не терять место."""
        response = self.client.post(reverse("teams:lead_add"), {
            "intern": self.person.pk, "project": self.project.pk,
            "next": self.person.get_absolute_url(),
        })
        self.assertRedirects(response, self.person.get_absolute_url())

    def test_assign_lead_ignores_unsafe_next_url(self):
        response = self.client.post(reverse("teams:lead_add"), {
            "intern": self.person.pk, "project": self.project.pk,
            "next": "https://evil.example.com/",
        })
        self.assertRedirects(response, reverse("teams:lead_list"))


class InternDetailLeadPromotionTests(TestCase):
    """Со страницы стажёра можно сразу сделать его тимлидом на проекте —
    раньше это было можно только через отдельную страницу «Тимлиды»."""

    def setUp(self):
        from apps.projects.services import create_project
        from apps.training.models import Specialization

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Балажан"))
        self.spec = Specialization.objects.create(name="UX/UI")
        self.person = Intern.objects.create(
            full_name="Макамбаева Айжаз", specialization=self.spec,
        )

    def test_button_shown_for_regular_member(self):
        TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.UXUI,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(self.person.get_absolute_url())
        self.assertContains(response, "Сделать тимлидом")

    def test_button_hidden_when_already_lead(self):
        TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(self.person.get_absolute_url())
        self.assertNotContains(response, "Сделать тимлидом")

    def test_promoting_from_intern_page_sets_lead_role_and_returns(self):
        member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.UXUI,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.post(reverse("teams:lead_add"), {
            "intern": self.person.pk, "project": self.project.pk,
            "next": self.person.get_absolute_url(),
        })
        self.assertRedirects(response, self.person.get_absolute_url())
        member.refresh_from_db()
        self.assertEqual(member.role, TeamRole.TEAM_LEAD)


class PMSectionTests(TestCase):
    """Раздел «ПМ»: отдельный отфильтрованный список — не нужно искать
    руководителей проектов в общем списке стажёров."""

    def setUp(self):
        from apps.projects.services import create_project

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Балажан"))
        self.person = Intern.objects.create(full_name="Болотбекова Умутай")

    def test_page_lists_pms(self):
        TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.PROJECT_MANAGER,
        )
        response = self.client.get(reverse("teams:pm_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Болотбекова Умутай")
        self.assertEqual(response.context["total"], 1)

    def test_assign_pm(self):
        self.client.post(reverse("teams:pm_add"), {
            "intern": self.person.pk, "project": self.project.pk,
        })
        member = TeamMember.objects.get(project=self.project, intern=self.person)
        self.assertEqual(member.role, TeamRole.PROJECT_MANAGER)

    def test_existing_member_becomes_pm(self):
        member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.BACKEND,
        )
        self.client.post(reverse("teams:pm_add"), {
            "intern": self.person.pk, "project": self.project.pk,
        })
        member.refresh_from_db()
        self.assertEqual(member.role, TeamRole.PROJECT_MANAGER)

    def test_remove_pm_keeps_person(self):
        member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.PROJECT_MANAGER,
        )
        self.client.post(reverse("teams:pm_remove", args=[member.pk]))
        self.assertFalse(TeamMember.objects.filter(pk=member.pk).exists())
        self.assertTrue(Intern.objects.filter(pk=self.person.pk).exists())

    def test_pm_not_shown_on_lead_page(self):
        TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.PROJECT_MANAGER,
        )
        response = self.client.get(reverse("teams:lead_list"))
        self.assertNotContains(response, "Болотбекова Умутай")


class InternDeleteTests(TestCase):
    """Стажёра можно удалить из базы."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.person = Intern.objects.create(full_name="Тестовый Человек")

    def test_delete_removes_person(self):
        response = self.client.post(
            reverse("interns:delete", args=[self.person.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Intern.objects.filter(pk=self.person.pk).exists())

    def test_get_does_not_delete(self):
        self.client.get(reverse("interns:delete", args=[self.person.pk]))
        self.assertTrue(Intern.objects.filter(pk=self.person.pk).exists())

    def test_delete_removes_team_memberships(self):
        from apps.projects.services import create_project

        project = create_project(Project(name="Омур"))
        TeamMember.objects.create(
            project=project, intern=self.person, role=TeamRole.BACKEND,
        )
        self.client.post(reverse("interns:delete", args=[self.person.pk]))
        self.assertEqual(project.team_members.count(), 0)


class MemberDeleteTests(TestCase):
    """Участника можно убрать из команды, команду — расформировать."""

    def setUp(self):
        from apps.projects.services import create_project

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Биклин"))
        self.person = Intern.objects.create(full_name="Алтынай")
        self.member = TeamMember.objects.create(
            project=self.project, intern=self.person, role=TeamRole.PROJECT_MANAGER,
        )

    def test_member_removed_person_stays(self):
        response = self.client.post(
            reverse("teams:member_delete", args=[self.member.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TeamMember.objects.filter(pk=self.member.pk).exists())
        self.assertTrue(Intern.objects.filter(pk=self.person.pk).exists())

    def test_get_does_not_remove_member(self):
        self.client.get(reverse("teams:member_delete", args=[self.member.pk]))
        self.assertTrue(TeamMember.objects.filter(pk=self.member.pk).exists())

    def test_team_cleared(self):
        other = Intern.objects.create(full_name="Бекназар")
        TeamMember.objects.create(
            project=self.project, intern=other, role=TeamRole.BACKEND,
        )
        self.client.post(reverse("teams:team_clear", args=[self.project.pk]))
        self.assertEqual(self.project.team_members.count(), 0)
        self.assertEqual(Intern.objects.count(), 2)

    def test_duplicate_membership_removed_by_command(self):
        from django.core.management import call_command

        TeamMember.objects.create(
            project=self.project, intern=self.person,
            role=TeamRole.PROJECT_MANAGER,
        )
        self.assertEqual(self.project.team_members.count(), 2)
        call_command("dedupe_members", verbosity=0)
        self.assertEqual(self.project.team_members.count(), 1)
