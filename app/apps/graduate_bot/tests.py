from django.test import TestCase

from apps.graduate_bot import services
from apps.interns.models import GraduateStatus, Intern, InternStatus
from apps.projects.models import Project, ProjectStageKey, ProjectStatus
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization


class FindGraduatesTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Балажан", status=ProjectStatus.COMPLETED)
        self.grad = Intern.objects.create(
            full_name="Сабыралиева Даяна Нурдиновна", graduate_status=GraduateStatus.PENDING,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.grad, role=TeamRole.UXUI,
            status=TeamMember.Status.LEFT,
        )
        self.non_graduate = Intern.objects.create(full_name="Активный Стажёров")

    def test_finds_by_partial_name_case_insensitive(self):
        result = services.find_graduates("даяна")
        self.assertEqual([i.pk for i in result], [self.grad.pk])

    def test_no_match_returns_empty(self):
        self.assertEqual(services.find_graduates("Неизвестный Человек"), [])

    def test_non_graduate_not_found(self):
        self.assertEqual(services.find_graduates("Активный"), [])

    def test_blank_name_returns_empty(self):
        self.assertEqual(services.find_graduates("   "), [])


class PhoneMatchesTests(TestCase):
    def setUp(self):
        self.intern = Intern.objects.create(full_name="Тест Тестов", phone="0501644171")

    def test_exact_match(self):
        self.assertTrue(services.phone_matches(self.intern, "0501644171"))

    def test_matches_with_country_code_and_formatting(self):
        self.assertTrue(services.phone_matches(self.intern, "+996 501 644 171"))
        self.assertTrue(services.phone_matches(self.intern, "996-501-644-171"))

    def test_mismatch(self):
        self.assertFalse(services.phone_matches(self.intern, "0501644172"))

    def test_too_short_does_not_match(self):
        self.assertFalse(services.phone_matches(self.intern, "1234"))


class EligibleProjectsTests(TestCase):
    def _project(self, name, stage, team_size, status=ProjectStatus.ACTIVE):
        project = Project.objects.create(name=name, status=status, current_stage=stage)
        for i in range(team_size):
            TeamMember.objects.create(
                project=project, intern=Intern.objects.create(full_name=f"{name} чел {i}"),
                role=TeamRole.BACKEND, status=TeamMember.Status.ACTIVE,
            )
        return project

    def test_dev_stage_with_room_is_eligible(self):
        project = self._project("Есть место", ProjectStageKey.BACKEND, team_size=3)
        self.assertIn(project, services.eligible_projects())

    def test_full_team_is_not_eligible(self):
        project = self._project("Полная команда", ProjectStageKey.BACKEND, team_size=4)
        self.assertNotIn(project, services.eligible_projects())

    def test_staging_stage_is_not_eligible(self):
        project = self._project("На тестовом", ProjectStageKey.STAGING, team_size=1)
        self.assertNotIn(project, services.eligible_projects())

    def test_paused_project_is_not_eligible(self):
        project = self._project(
            "На паузе", ProjectStageKey.BACKEND, team_size=1, status=ProjectStatus.PAUSED,
        )
        self.assertNotIn(project, services.eligible_projects())

    def test_left_members_do_not_count_toward_team_size(self):
        project = Project.objects.create(
            name="С вышедшими", status=ProjectStatus.ACTIVE, current_stage=ProjectStageKey.BACKEND,
        )
        for i in range(5):
            TeamMember.objects.create(
                project=project, intern=Intern.objects.create(full_name=f"Вышедший {i}"),
                role=TeamRole.BACKEND, status=TeamMember.Status.LEFT,
            )
        self.assertIn(project, services.eligible_projects())


class JoinGraduateToProjectTests(TestCase):
    def setUp(self):
        self.spec = Specialization.objects.create(name="Backend")
        self.project = Project.objects.create(name="Новый проект")
        self.intern = Intern.objects.create(
            full_name="Выпускник Тестов", specialization=self.spec,
            status=InternStatus.READY, graduate_status=GraduateStatus.PENDING,
        )

    def test_creates_active_membership_with_role_from_specialization(self):
        member = services.join_graduate_to_project(self.intern, self.project)
        self.assertEqual(member.role, TeamRole.BACKEND)
        self.assertEqual(member.status, TeamMember.Status.ACTIVE)
        self.assertEqual(member.project, self.project)

    def test_clears_graduate_status_and_activates(self):
        services.join_graduate_to_project(self.intern, self.project)
        self.intern.refresh_from_db()
        self.assertEqual(self.intern.graduate_status, "")
        self.assertEqual(self.intern.status, InternStatus.ACTIVE)

    def test_logs_to_audit(self):
        from apps.audit.models import AuditLog

        services.join_graduate_to_project(self.intern, self.project)
        entry = AuditLog.objects.get(
            object_type="Intern", object_id=str(self.intern.pk),
            action="Статус выпускника снят",
        )
        self.assertIn("Новый проект", entry.reason)
        self.assertIn("бот-выпускник", entry.reason)


class TeamLeadContactTests(TestCase):
    def setUp(self):
        self.backend = Specialization.objects.create(name="Backend")
        self.frontend = Specialization.objects.create(name="Frontend")
        self.project = Project.objects.create(name="Проект")
        self.backend_lead = Intern.objects.create(
            full_name="Бэкенд Тимлид", specialization=self.backend,
        )
        self.frontend_lead = Intern.objects.create(
            full_name="Фронтенд Тимлид", specialization=self.frontend,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.backend_lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.frontend_lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        self.graduate = Intern.objects.create(full_name="Выпускник", specialization=self.backend)

    def test_matches_lead_of_own_direction(self):
        contact = services.team_lead_contact(self.project, self.graduate)
        self.assertEqual(contact, self.backend_lead)

    def test_falls_back_to_any_lead_without_specialization(self):
        self.graduate.specialization = None
        self.graduate.save(update_fields=["specialization"])
        contact = services.team_lead_contact(self.project, self.graduate)
        self.assertIn(contact, [self.backend_lead, self.frontend_lead])

    def test_none_when_no_lead(self):
        empty_project = Project.objects.create(name="Без тимлида")
        self.assertIsNone(services.team_lead_contact(empty_project, self.graduate))
