from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole

Model = get_user_model()


class LeadProjectOwnershipTests(TestCase):
    """Тимлид видит только тот проект, где сам активный
    TeamMember(role='team_lead')."""

    def setUp(self):
        self.lead_user = Model.objects.create_user(
            username="+996700000030", password="x", role=User.Role.TEAM_LEAD,
        )
        self.lead_intern = Intern.objects.create(
            full_name="Тестов Тимлид", user=self.lead_user,
        )
        self.project_a = Project.objects.create(name="Проект A")
        self.project_b = Project.objects.create(name="Проект B")
        TeamMember.objects.create(
            project=self.project_a, intern=self.lead_intern, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.force_login(self.lead_user)

    def test_dashboard_lists_only_own_project(self):
        response = self.client.get(reverse("lead_portal:dashboard"))
        names = [p.name for p in response.context["projects"]]
        self.assertEqual(names, ["Проект A"])

    def test_can_open_own_project(self):
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_a.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Проект A")

    def test_cannot_open_foreign_project(self):
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_left_membership_does_not_grant_access(self):
        TeamMember.objects.create(
            project=self.project_b, intern=self.lead_intern, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.LEFT,
        )
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_non_lead_role_on_project_does_not_grant_access(self):
        """Например, бэкендер на проекте — не тимлид, доступа нет."""
        TeamMember.objects.create(
            project=self.project_b, intern=self.lead_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_overview_tab_has_no_client_or_documents_links(self):
        """Клиент/документы/отчёты — не в компетенции тимлида, их
        вкладок в портале тимлида вообще нет."""
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_a.pk]),
        )
        self.assertNotContains(response, "Клиент")
        self.assertNotContains(response, "Документы")
        self.assertNotContains(response, "Отчёт")


class LeadTeamManagementTests(LeadProjectOwnershipTests):
    """Команда: тимлид может добавлять/править/убирать людей своего
    проекта, ничего на чужом."""

    def test_can_add_member_to_own_project(self):
        other = Intern.objects.create(full_name="Новый Бэкендер")
        self.client.post(
            reverse("lead_portal:member_add", args=[self.project_a.pk]),
            {"intern": other.pk},
        )
        self.assertTrue(
            TeamMember.objects.filter(project=self.project_a, intern=other).exists(),
        )

    def test_cannot_add_member_to_foreign_project(self):
        other = Intern.objects.create(full_name="Чужой Бэкендер")
        response = self.client.post(
            reverse("lead_portal:member_add", args=[self.project_b.pk]),
            {"intern": other.pk},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            TeamMember.objects.filter(project=self.project_b, intern=other).exists(),
        )

    def test_can_edit_member_on_own_project(self):
        intern = Intern.objects.create(full_name="Правим")
        member = TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.post(
            reverse("lead_portal:member_edit", args=[self.project_a.pk, member.pk]),
            {"intern": intern.pk, "status": "active", "comment": "правим тут"},
        )
        member.refresh_from_db()
        self.assertEqual(member.comment, "правим тут")

    def test_can_remove_member_from_own_project(self):
        intern = Intern.objects.create(full_name="Снимаемый")
        member = TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        self.client.post(
            reverse("lead_portal:member_delete", args=[self.project_a.pk, member.pk]),
        )
        self.assertFalse(TeamMember.objects.filter(pk=member.pk).exists())

    def test_team_tab_shows_only_own_project_members(self):
        intern = Intern.objects.create(full_name="Участник А")
        TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_a.pk]) + "?tab=team",
        )
        self.assertContains(response, "Участник А")


class LeadAttendanceTests(TestCase):
    """Табель — только по группе своего проекта, полный доступ (как у ПМ)."""

    def setUp(self):
        from apps.flows.models import Flow, Group

        self.lead_user = Model.objects.create_user(
            username="+996700000040", password="x", role=User.Role.TEAM_LEAD,
        )
        self.lead_intern = Intern.objects.create(
            full_name="Тимлид Табельный", user=self.lead_user,
        )
        self.project_a = Project.objects.create(name="Проект С группой")
        self.project_b = Project.objects.create(name="Проект без доступа")
        flow = Flow.objects.create(number=1, status=Flow.Status.ACTIVE)
        self.group = Group.objects.create(flow=flow, number=1, project=self.project_a)
        TeamMember.objects.create(
            project=self.project_a, group=self.group, intern=self.lead_intern,
            role=TeamRole.TEAM_LEAD, status=TeamMember.Status.ACTIVE,
        )
        self.client.force_login(self.lead_user)

    def test_no_group_shows_empty_state(self):
        TeamMember.objects.create(
            project=self.project_b, intern=self.lead_intern, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project_b.pk]) + "?tab=attendance",
        )
        self.assertContains(response, "ещё не назначена")

    def test_can_create_meeting_for_own_group(self):
        from apps.attendance.models import GroupMeeting

        self.client.post(
            reverse("lead_portal:meeting_create", args=[self.project_a.pk]),
            {"date": "2026-09-10"},
        )
        self.assertTrue(GroupMeeting.objects.filter(group=self.group).exists())

    def test_can_mark_attendance_and_score_activity(self):
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind, WorkScore

        member_intern = Intern.objects.create(full_name="Отмечаемый")
        TeamMember.objects.create(
            project=self.project_a, group=self.group, intern=member_intern,
            role=TeamRole.BACKEND, status=TeamMember.Status.ACTIVE,
        )
        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL,
            date=__import__("datetime").date(2026, 9, 10),
        )
        self.client.post(
            reverse(
                "lead_portal:meeting_mark_toggle",
                args=[self.project_a.pk, meeting.pk],
            ),
            {"intern": member_intern.pk},
        )
        self.client.post(
            reverse("lead_portal:meeting_score", args=[self.project_a.pk, meeting.pk]),
            {"intern": member_intern.pk, "score": "8"},
        )
        self.assertTrue(
            WorkScore.objects.filter(meeting=meeting, intern=member_intern, score=8).exists(),
        )

    def test_cannot_reach_meeting_from_foreign_group(self):
        from apps.flows.models import Flow, Group
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind

        TeamMember.objects.create(
            project=self.project_b, intern=self.lead_intern, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        flow = Flow.objects.create(number=2, status=Flow.Status.ACTIVE)
        foreign_group = Group.objects.create(flow=flow, number=1, project=None)
        meeting = attendance_services.create_meeting(
            foreign_group, kind=MeetingKind.INTERNAL,
            date=__import__("datetime").date(2026, 9, 10),
        )
        response = self.client.get(
            reverse(
                "lead_portal:meeting_detail",
                args=[self.project_a.pk, meeting.pk],
            ),
        )
        self.assertEqual(response.status_code, 404)


class LeadInternDetailTests(LeadProjectOwnershipTests):
    """Карточка стажёра — только по своему проекту, только чтение."""

    def test_can_view_own_project_intern(self):
        intern = Intern.objects.create(full_name="Видимый Стажёр")
        TeamMember.objects.create(
            project=self.project_a, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("lead_portal:intern_detail", args=[self.project_a.pk, intern.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Видимый Стажёр")

    def test_cannot_view_foreign_project_intern(self):
        intern = Intern.objects.create(full_name="Чужой Стажёр")
        TeamMember.objects.create(
            project=self.project_b, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("lead_portal:intern_detail", args=[self.project_a.pk, intern.pk]),
        )
        self.assertEqual(response.status_code, 404)


class LeadPortalExcludedActionsTests(TestCase):
    """Статус/этап/дедлайн, отчёты, документы, клиент — этих урлов в
    портале тимлида просто нет (в отличие от ПМ-портала)."""

    def test_no_report_document_client_or_stage_urls(self):
        from django.urls import NoReverseMatch

        for name in (
            "lead_portal:report_create", "lead_portal:document_upload",
            "lead_portal:client_edit", "lead_portal:stage_set",
        ):
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=[1])
