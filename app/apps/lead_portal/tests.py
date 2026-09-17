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


class LeadResumeTests(TestCase):
    """Тимлид сам ведёт своё резюме в резерве кадров — под логином, без ссылок."""

    def setUp(self):
        from apps.reserve.models import CandidateStatus, ReserveCandidate

        self.lead_user = Model.objects.create_user(
            username="+996700000040", password="x", role=User.Role.TEAM_LEAD,
        )
        self.lead = Intern.objects.create(full_name="Резюмеев Тимлид", user=self.lead_user)
        self.project = Project.objects.create(name="Омур")
        TeamMember.objects.create(
            project=self.project, intern=self.lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        self.card = ReserveCandidate.objects.create(
            full_name="Резюмеев Тимлид", phone="0700111222", intern=self.lead,
            skills="Python", status=CandidateStatus.RESERVE, rating=7,
            comment_pm="внутренний комментарий", consent_given=True,
        )
        self.url = reverse("lead_portal:resume")
        self.client.force_login(self.lead_user)

    def _payload(self, **extra):
        return {
            "full_name": "Резюмеев Тимлид", "phone": "0700111222",
            "skills": "Python, Django, Docker", "desired_position": "Team Lead",
            "consent_given": "on", **extra,
        }

    def test_lead_sees_own_resume(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["candidate"], self.card)
        self.assertContains(response, "Сохранить резюме")
        self.assertNotContains(response, "внутренний комментарий")

    def test_lead_updates_resume(self):
        response = self.client.post(self.url, self._payload())
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.card.refresh_from_db()
        self.assertEqual(self.card.skills, "Python, Django, Docker")
        self.assertEqual(self.card.desired_position, "Team Lead")
        self.assertIsNotNone(self.card.submitted_at)
        self.assertEqual(self.card.updated_by, self.lead_user)
        self.assertTrue(
            self.card.events.filter(title="Кандидат обновил резюме в своём портале").exists()
        )

    def test_lead_cannot_touch_internal_fields(self):
        self.client.post(self.url, self._payload(
            status="employed", rating="10", comment_pm="всё отлично", intern="",
        ))
        self.card.refresh_from_db()
        self.assertEqual(self.card.status, "reserve")
        self.assertEqual(self.card.rating, 7)
        self.assertEqual(self.card.comment_pm, "внутренний комментарий")
        self.assertEqual(self.card.intern, self.lead)

    def test_dashboard_shows_resume_card(self):
        response = self.client.get(reverse("lead_portal:dashboard"))
        self.assertContains(response, "Моё резюме в резерве кадров")

    def test_without_reserve_card_shows_empty_state(self):
        self.card.intern = None
        self.card.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["candidate"])
        self.assertContains(response, "Вас пока нет в резерве кадров")
        self.client.post(self.url, self._payload(skills="взлом"))
        self.card.refresh_from_db()
        self.assertEqual(self.card.skills, "Python")

    def test_cannot_edit_someone_elses_resume(self):
        other_user = Model.objects.create_user(
            username="+996700000041", password="x", role=User.Role.TEAM_LEAD,
        )
        Intern.objects.create(full_name="Другой", user=other_user)
        self.client.force_login(other_user)
        self.client.post(self.url, self._payload(skills="чужое"))
        self.card.refresh_from_db()
        self.assertEqual(self.card.skills, "Python")

    def test_pm_is_kept_out_of_lead_resume(self):
        pm = Model.objects.create_user(
            username="+996700000042", password="x", role=User.Role.PROJECT_MANAGER,
        )
        self.client.force_login(pm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_archived_lead_in_reserve_keeps_login_for_resume(self):
        from apps.interns.services import archive_person

        archive_person(self.lead)
        self.lead_user.refresh_from_db()
        self.assertTrue(self.lead_user.is_active)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        # но команды у него больше нет
        response = self.client.get(
            reverse("lead_portal:project_detail", args=[self.project.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_archived_lead_without_reserve_loses_login(self):
        from apps.interns.services import archive_person

        self.card.delete()
        archive_person(self.lead)
        self.lead_user.refresh_from_db()
        self.assertFalse(self.lead_user.is_active)


class LeadProjectClosedNotificationTests(TestCase):
    """Проект завершён или закрыт — тимлиду приходит уведомление в портал."""

    def setUp(self):
        self.lead_user = Model.objects.create_user(
            username="+996700000050", password="x", role=User.Role.TEAM_LEAD,
        )
        self.lead = Intern.objects.create(full_name="Уведомлёнов Тимлид", user=self.lead_user)
        self.intern = Intern.objects.create(full_name="Просто Стажёр")
        self.old_lead = Intern.objects.create(full_name="Ушедший Тимлид")
        self.project = Project.objects.create(name="Омур")
        TeamMember.objects.create(
            project=self.project, intern=self.lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.intern, role=TeamRole.OTHER,
            status=TeamMember.Status.ACTIVE,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.old_lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.LEFT,
        )
        self.client.force_login(self.lead_user)

    def _close(self, status):
        from apps.projects.services import update_project

        self.project.status = status
        update_project(self.project, {"status": "active"})

    def test_completed_project_notifies_lead(self):
        from apps.notifications.models import Notification

        self._close("completed")
        note = Notification.objects.get(intern=self.lead)
        self.assertEqual(note.title, "Проект «Омур» завершён")
        self.assertEqual(note.level, "success")

    def test_cancelled_and_refused_projects_notify_lead(self):
        from apps.notifications.models import Notification

        self._close("cancelled")
        self.assertEqual(
            Notification.objects.get(intern=self.lead).title,
            "Проект «Омур» закрыт: отменён",
        )

    def test_only_active_leads_are_notified(self):
        from apps.notifications.models import Notification

        self._close("completed")
        self.assertFalse(Notification.objects.filter(intern=self.intern).exists())
        self.assertFalse(Notification.objects.filter(intern=self.old_lead).exists())

    def test_pause_does_not_notify(self):
        from apps.notifications.models import Notification

        self._close("paused")
        self.assertFalse(Notification.objects.filter(intern=self.lead).exists())

    def test_force_complete_notifies_lead(self):
        from apps.notifications.models import Notification
        from apps.projects.delivery import complete_project

        complete_project(self.project, force=True, reason="сдали вручную")
        self.assertTrue(
            Notification.objects.filter(intern=self.lead, title__endswith="завершён").exists()
        )

    def test_personal_notification_stays_out_of_head_feed(self):
        from apps.notifications import services

        self._close("completed")
        self.assertEqual(services.unread_count(), 0)
        self.assertFalse(services.feed().exists())

    def test_dashboard_shows_marks_read_and_close_hides(self):
        from apps.notifications.models import Notification

        self._close("completed")
        response = self.client.get(reverse("lead_portal:dashboard"))
        self.assertContains(response, "Проект «Омур» завершён")
        note = Notification.objects.get(intern=self.lead)
        self.assertTrue(note.is_read)
        self.client.post(reverse("lead_portal:notification_close", args=[note.pk]))
        response = self.client.get(reverse("lead_portal:dashboard"))
        self.assertNotContains(response, "Проект «Омур» завершён")

    def test_cannot_close_someone_elses_notification(self):
        from apps.notifications.services import notify

        note = notify("Чужое", intern=self.intern)
        self.client.post(reverse("lead_portal:notification_close", args=[note.pk]))
        note.refresh_from_db()
        self.assertFalse(note.is_closed)

    def test_notification_waits_for_login(self):
        """Логин выдали позже — уведомление уже ждёт в портале."""
        from apps.notifications.models import Notification

        late = Intern.objects.create(full_name="Без Логина")
        TeamMember.objects.create(
            project=self.project, intern=late, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        self._close("completed")
        self.assertTrue(Notification.objects.filter(intern=late).exists())
        user = Model.objects.create_user(
            username="+996700000051", password="x", role=User.Role.TEAM_LEAD,
        )
        late.user = user
        late.save()
        self.client.force_login(user)
        self.assertContains(
            self.client.get(reverse("lead_portal:dashboard")), "Проект «Омур» завершён",
        )



class LeadProfileLinkTests(LeadProjectOwnershipTests):
    """Тимлид сам выпускает ссылку на анкету для новых стажёров проекта."""

    def setUp(self):
        super().setUp()
        from apps.training.models import Specialization

        self.spec = Specialization.objects.create(name="Backend")
        self.team_url = (
            reverse("lead_portal:project_detail", args=[self.project_a.pk]) + "?tab=team"
        )

    def _payload(self, **overrides):
        data = {
            "full_name": "Новый Бэкендер", "phone": "0700777888",
            "email": "new@example.com", "telegram": "@newbe",
            "city": "Бишкек", "branch": "Бишкек", "specialization": self.spec.pk,
            "education_end_date": "2026-06-01", "internship_start_date": "2026-07-01",
            "internship_attempt": "1",
        }
        data.update(overrides)
        return data

    def _create_link(self, project=None):
        project = project or self.project_a
        return self.client.post(
            reverse("lead_portal:profile_link_create", args=[project.pk]), {"ttl_days": "7"},
        )

    def test_lead_creates_link_bound_to_project(self):
        from apps.interns.models import ProfileFormLink

        response = self._create_link()
        self.assertRedirects(response, self.team_url, fetch_redirect_response=False)
        link = ProfileFormLink.objects.get(is_active=True, project=self.project_a)
        self.assertEqual(link.created_by, self.lead_user)
        self.assertIsNotNone(link.expires_at)
        page = self.client.get(self.team_url)
        self.assertContains(page, link.get_absolute_url())

    def test_cannot_create_link_for_foreign_project(self):
        from apps.interns.models import ProfileFormLink

        self.assertEqual(self._create_link(self.project_b).status_code, 404)
        self.assertFalse(ProfileFormLink.objects.filter(project=self.project_b).exists())

    def test_new_link_replaces_only_this_projects_link(self):
        from apps.interns import services as intern_services
        from apps.interns.models import ProfileFormLink

        general = intern_services.issue_profile_form_link()
        other = intern_services.issue_profile_form_link(project=self.project_b)
        self._create_link()
        first = ProfileFormLink.objects.get(is_active=True, project=self.project_a)
        self._create_link()
        first.refresh_from_db()
        general.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(general.is_active)
        self.assertTrue(other.is_active)

    def test_head_general_link_does_not_kill_project_links(self):
        from apps.interns import services as intern_services
        from apps.interns.models import ProfileFormLink

        self._create_link()
        intern_services.issue_profile_form_link()
        self.assertTrue(
            ProfileFormLink.objects.filter(is_active=True, project=self.project_a).exists()
        )

    def test_disable_link(self):
        from apps.interns.models import ProfileFormLink

        self._create_link()
        self.client.post(reverse("lead_portal:profile_link_disable", args=[self.project_a.pk]))
        self.assertFalse(
            ProfileFormLink.objects.filter(is_active=True, project=self.project_a).exists()
        )

    def test_filled_form_puts_person_into_project_team(self):
        from apps.interns.models import Intern as InternModel, ProfileFormLink
        from apps.notifications.models import Notification

        self._create_link()
        link = ProfileFormLink.objects.get(is_active=True, project=self.project_a)
        self.client.logout()
        response = self.client.post(
            reverse("intern_profile_apply", args=[link.token]), self._payload(),
        )
        self.assertEqual(response.status_code, 200)
        person = InternModel.objects.get(phone="0700777888")
        member = TeamMember.objects.get(project=self.project_a, intern=person)
        self.assertEqual(member.status, TeamMember.Status.ACTIVE)
        self.assertEqual(member.role, TeamRole.BACKEND)
        self.assertIsNotNone(member.joined_at)
        self.assertEqual(person.status, "active")
        note = Notification.objects.get(intern=self.lead_intern)
        self.assertIn("Новый Бэкендер", note.title)
        self.assertIn("Проект A", note.title)

    def test_refilled_form_does_not_duplicate_membership(self):
        from apps.interns.models import Intern as InternModel, ProfileFormLink

        self._create_link()
        link = ProfileFormLink.objects.get(is_active=True, project=self.project_a)
        self.client.logout()
        url = reverse("intern_profile_apply", args=[link.token])
        self.client.post(url, self._payload())
        self.client.session.flush()
        other = self.client_class()
        other.post(url, self._payload())
        person = InternModel.objects.get(phone="0700777888")
        self.assertEqual(
            TeamMember.objects.filter(project=self.project_a, intern=person).count(), 1,
        )

    def test_general_link_does_not_add_to_any_team(self):
        from apps.interns import services as intern_services
        from apps.interns.models import Intern as InternModel

        link = intern_services.issue_profile_form_link()
        self.client.logout()
        self.client.post(reverse("intern_profile_apply", args=[link.token]), self._payload())
        person = InternModel.objects.get(phone="0700777888")
        self.assertFalse(person.team_memberships.exists())
