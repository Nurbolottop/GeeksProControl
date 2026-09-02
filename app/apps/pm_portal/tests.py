import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole

Model = get_user_model()


class PmProjectOwnershipTests(TestCase):
    """ПМ видит только тот проект, где сам активный TeamMember(role='pm')."""

    def setUp(self):
        self.pm_user = Model.objects.create_user(
            username="+996700000010", password="x", role=User.Role.PROJECT_MANAGER,
        )
        self.pm_intern = Intern.objects.create(
            full_name="Тестов ПМ", user=self.pm_user,
        )
        self.project_a = Project.objects.create(name="Проект A")
        self.project_b = Project.objects.create(name="Проект B")
        TeamMember.objects.create(
            project=self.project_a, intern=self.pm_intern, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.force_login(self.pm_user)

    def test_dashboard_lists_only_own_project(self):
        response = self.client.get(reverse("pm_portal:dashboard"))
        names = [p.name for p in response.context["projects"]]
        self.assertEqual(names, ["Проект A"])

    def test_can_open_own_project(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Проект A")

    def test_cannot_open_foreign_project(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_left_membership_does_not_grant_access(self):
        TeamMember.objects.create(
            project=self.project_b, intern=self.pm_intern, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.LEFT,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_non_pm_role_on_project_does_not_grant_access(self):
        """Например, тимлид или бэкендер на проекте — не ПМ, доступа нет."""
        TeamMember.objects.create(
            project=self.project_b, intern=self.pm_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)


class PmReportTests(PmProjectOwnershipTests):
    """Отчёты — доступны только на своём проекте."""

    def test_can_create_report_on_own_project(self):
        from apps.projects.models import ProjectReport

        self.client.post(
            reverse("pm_portal:report_create", args=[self.project_a.pk]),
            {"text": "Сделали бэкенд, начали фронт."},
        )
        report = ProjectReport.objects.get(project=self.project_a)
        self.assertEqual(report.author, self.pm_user)

    def test_cannot_create_report_on_foreign_project(self):
        from apps.projects.models import ProjectReport

        response = self.client.post(
            reverse("pm_portal:report_create", args=[self.project_b.pk]),
            {"text": "Не мой проект."},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProjectReport.objects.filter(project=self.project_b).exists())

    def test_cannot_edit_report_by_guessing_id_from_other_project(self):
        from apps.projects.models import ProjectReport

        foreign_report = ProjectReport.objects.create(
            project=self.project_b, text="Чужой отчёт",
        )
        response = self.client.post(
            reverse(
                "pm_portal:report_update",
                args=[self.project_a.pk, foreign_report.pk],
            ),
            {"text": "Подмена"},
        )
        self.assertEqual(response.status_code, 404)
        foreign_report.refresh_from_db()
        self.assertEqual(foreign_report.text, "Чужой отчёт")


class PmTeamManagementTests(PmProjectOwnershipTests):
    """Команда: полное управление своим проектом, ничего на чужом."""

    def test_can_add_member_to_own_project(self):
        other = Intern.objects.create(full_name="Новый Бэкендер")
        self.client.post(
            reverse("pm_portal:member_add", args=[self.project_a.pk]),
            {"intern": other.pk},
        )
        self.assertTrue(
            TeamMember.objects.filter(project=self.project_a, intern=other).exists(),
        )

    def test_cannot_add_member_to_foreign_project(self):
        other = Intern.objects.create(full_name="Чужой Бэкендер")
        response = self.client.post(
            reverse("pm_portal:member_add", args=[self.project_b.pk]),
            {"intern": other.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            TeamMember.objects.filter(project=self.project_b, intern=other).exists(),
        )

    def test_cannot_edit_member_from_other_project_via_own_project_url(self):
        foreign_intern = Intern.objects.create(full_name="Чужой Участник")
        foreign_member = TeamMember.objects.create(
            project=self.project_b, intern=foreign_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse(
                "pm_portal:member_edit",
                args=[self.project_a.pk, foreign_member.pk],
            ),
        )
        self.assertEqual(response.status_code, 404)

    def test_can_remove_member_from_own_project(self):
        intern = Intern.objects.create(full_name="Снимаемый")
        member = TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.post(
            reverse("pm_portal:member_delete", args=[self.project_a.pk, member.pk]),
        )
        self.assertFalse(TeamMember.objects.filter(pk=member.pk).exists())

    def test_team_tab_shows_only_own_project_members(self):
        intern = Intern.objects.create(full_name="Участник А")
        TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=team",
        )
        self.assertContains(response, "Участник А")


class PmAttendanceTests(TestCase):
    """Табель — только по группе своего проекта."""

    def setUp(self):
        from apps.flows.models import Flow, Group

        self.pm_user = Model.objects.create_user(
            username="+996700000020", password="x", role=User.Role.PROJECT_MANAGER,
        )
        self.pm_intern = Intern.objects.create(
            full_name="Тестов ПМ2", user=self.pm_user,
        )
        self.project_a = Project.objects.create(name="Проект С группой")
        self.project_b = Project.objects.create(name="Проект без доступа")
        flow = Flow.objects.create(number=1, status=Flow.Status.ACTIVE)
        self.group = Group.objects.create(flow=flow, number=1, project=self.project_a)
        TeamMember.objects.create(
            project=self.project_a, group=self.group, intern=self.pm_intern,
            role=TeamRole.PROJECT_MANAGER, status=TeamMember.Status.ACTIVE,
        )
        self.client.force_login(self.pm_user)

    def test_no_group_shows_empty_state(self):
        TeamMember.objects.create(
            project=self.project_b, intern=self.pm_intern, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_b.pk]) + "?tab=attendance",
        )
        self.assertContains(response, "ещё не назначена")

    def test_can_create_meeting_for_own_group(self):
        from apps.attendance.models import GroupMeeting

        self.client.post(
            reverse("pm_portal:meeting_create", args=[self.project_a.pk]),
            {"date": "2026-09-10"},
        )
        self.assertTrue(GroupMeeting.objects.filter(group=self.group).exists())

    def test_cannot_reach_meeting_from_foreign_group(self):
        from apps.flows.models import Flow, Group
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind

        other_flow = Flow.objects.create(number=2, status=Flow.Status.ACTIVE)
        other_group = Group.objects.create(
            flow=other_flow, number=1, project=self.project_b,
        )
        meeting = attendance_services.create_meeting(
            other_group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        response = self.client.get(
            reverse("pm_portal:meeting_detail", args=[self.project_a.pk, meeting.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_toggle_mark_creates_attendance(self):
        from apps.attendance import services as attendance_services
        from apps.attendance.models import Attendance, MeetingKind

        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        self.client.post(
            reverse(
                "pm_portal:meeting_mark_toggle",
                args=[self.project_a.pk, meeting.pk],
            ),
            {"intern": self.pm_intern.pk},
        )
        self.assertTrue(
            Attendance.objects.filter(meeting=meeting, intern=self.pm_intern).exists(),
        )


class PmEvaluationTests(PmProjectOwnershipTests):
    """Оценки — только для тех, кто в команде своего проекта."""

    def test_can_evaluate_own_team_member(self):
        from apps.interns.models import InternEvaluation

        member_intern = Intern.objects.create(full_name="Оцениваемый")
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.post(
            reverse("pm_portal:evaluation_add", args=[self.project_a.pk, member_intern.pk]),
            {
                "hard_skills": 5, "quality": 5, "speed": 5, "responsibility": 5,
                "communication": 5, "teamwork": 5, "independence": 5,
                "comment": "Молодец",
            },
        )
        evaluation = InternEvaluation.objects.get(intern=member_intern)
        self.assertEqual(evaluation.project, self.project_a)
        self.assertEqual(evaluation.evaluator, self.pm_user)

    def test_cannot_evaluate_intern_not_on_own_project(self):
        outsider = Intern.objects.create(full_name="Не в команде")
        response = self.client.get(
            reverse("pm_portal:evaluation_add", args=[self.project_a.pk, outsider.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_evaluation_locked_to_own_project_even_if_posted(self):
        """Даже если подделать project в POST — сохранится свой проект."""
        from apps.interns.models import InternEvaluation

        member_intern = Intern.objects.create(full_name="Оцениваемый2")
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.post(
            reverse("pm_portal:evaluation_add", args=[self.project_a.pk, member_intern.pk]),
            {
                "project": self.project_b.pk,
                "hard_skills": 3, "quality": 3, "speed": 3, "responsibility": 3,
                "communication": 3, "teamwork": 3, "independence": 3,
            },
        )
        evaluation = InternEvaluation.objects.get(intern=member_intern)
        self.assertEqual(evaluation.project, self.project_a)
