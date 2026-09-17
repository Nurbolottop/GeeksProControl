import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

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

    def test_dashboard_status_filter(self):
        from apps.projects.models import ProjectStatus

        self.project_a.status = ProjectStatus.COMPLETED
        self.project_a.save(update_fields=["status"])

        response = self.client.get(reverse("pm_portal:dashboard"), {"status": "completed"})
        names = [p.name for p in response.context["projects"]]
        self.assertEqual(names, ["Проект A"])

        response = self.client.get(reverse("pm_portal:dashboard"), {"status": "in_progress"})
        names = [p.name for p in response.context["projects"]]
        self.assertEqual(names, [])

        response = self.client.get(reverse("pm_portal:dashboard"), {"status": "all"})
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
    """Команду ведут тимлиды: ПМ её только смотрит — добавлять, менять
    и убирать участников в портале ПМ нечем, маршрутов для этого нет."""

    def test_no_member_management_routes(self):
        for name, args in (
            ("pm_portal:member_add", [self.project_a.pk]),
            ("pm_portal:member_edit", [self.project_a.pk, 1]),
            ("pm_portal:member_delete", [self.project_a.pk, 1]),
        ):
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=args)

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
        self.assertContains(response, "здесь только просмотр")
        self.assertNotContains(response, "+ Участник")
        self.assertNotContains(response, "Убрать из команды")


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
        # ПМ/тимлид не отмечают посещаемость и не получают «Активность» —
        # для этого нужен обычный стажёр команды.
        self.dev_intern = Intern.objects.create(full_name="Стажёров Бэкендер")
        TeamMember.objects.create(
            project=self.project_a, group=self.group, intern=self.dev_intern,
            role=TeamRole.BACKEND, status=TeamMember.Status.ACTIVE,
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
            {"intern": self.dev_intern.pk},
        )
        self.assertTrue(
            Attendance.objects.filter(meeting=meeting, intern=self.dev_intern).exists(),
        )

    def test_toggle_mark_is_ajax_returns_partial_not_redirect(self):
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind

        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        response = self.client.post(
            reverse(
                "pm_portal:meeting_mark_toggle",
                args=[self.project_a.pk, meeting.pk],
            ),
            {"intern": self.dev_intern.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="mark-{self.dev_intern.pk}"')
        self.assertContains(response, "Был")

    def test_score_person_creates_work_score(self):
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind, WorkScore

        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        response = self.client.post(
            reverse("pm_portal:meeting_score", args=[self.project_a.pk, meeting.pk]),
            {"intern": self.dev_intern.pk, "score": "8"},
        )
        self.assertEqual(response.status_code, 200)
        score = WorkScore.objects.get(meeting=meeting, intern=self.dev_intern)
        self.assertEqual(score.score, 8)

    def test_pm_cannot_be_marked_or_scored(self):
        """ПМ/тимлид не отмечаются и не оцениваются — их вообще нет
        в табеле собрания."""
        from apps.attendance import services as attendance_services
        from apps.attendance.models import Attendance, MeetingKind, WorkScore

        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        mark_response = self.client.post(
            reverse(
                "pm_portal:meeting_mark_toggle",
                args=[self.project_a.pk, meeting.pk],
            ),
            {"intern": self.pm_intern.pk},
        )
        self.assertEqual(mark_response.status_code, 404)
        self.assertFalse(
            Attendance.objects.filter(meeting=meeting, intern=self.pm_intern).exists(),
        )

        score_response = self.client.post(
            reverse("pm_portal:meeting_score", args=[self.project_a.pk, meeting.pk]),
            {"intern": self.pm_intern.pk, "score": "8"},
        )
        self.assertEqual(score_response.status_code, 404)
        self.assertFalse(WorkScore.objects.filter(meeting=meeting, intern=self.pm_intern).exists())

        detail_response = self.client.get(
            reverse("pm_portal:meeting_detail", args=[self.project_a.pk, meeting.pk]),
        )
        self.assertNotContains(detail_response, "Project Manager")

    def test_cannot_score_on_foreign_project(self):
        from apps.flows.models import Flow, Group
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind, WorkScore

        other_flow = Flow.objects.create(number=3, status=Flow.Status.ACTIVE)
        other_group = Group.objects.create(
            flow=other_flow, number=1, project=self.project_b,
        )
        meeting = attendance_services.create_meeting(
            other_group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        response = self.client.post(
            reverse("pm_portal:meeting_score", args=[self.project_a.pk, meeting.pk]),
            {"intern": self.pm_intern.pk, "score": "8"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(WorkScore.objects.filter(meeting=meeting).exists())

    def test_meeting_detail_shows_grouped_scores_tab(self):
        from apps.attendance import services as attendance_services
        from apps.attendance.models import MeetingKind

        meeting = attendance_services.create_meeting(
            self.group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 10),
        )
        response = self.client.get(
            reverse("pm_portal:meeting_detail", args=[self.project_a.pk, meeting.pk]),
        )
        self.assertContains(response, "Активность")
        self.assertContains(response, "Backend")
        self.assertNotContains(response, "Project Manager")


class PmEvaluationTests(PmProjectOwnershipTests):
    """Ручных оценок в ПМ-портале больше нет — только «Активность» с собраний."""

    def test_no_evaluation_add_route_exists(self):
        with self.assertRaises(NoReverseMatch):
            reverse("pm_portal:evaluation_add", args=[self.project_a.pk, 1])

    def test_evaluations_tab_removed_from_project_detail(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]),
        )
        self.assertNotContains(response, "tab=evaluations")


class PmInternDetailTests(PmProjectOwnershipTests):
    """Детальная карточка стажёра — только по своей команде своего проекта."""

    def test_can_view_own_team_member_detail(self):
        member_intern = Intern.objects.create(
            full_name="Стажёров Детализируемый", phone="0700111222",
        )
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:intern_detail", args=[self.project_a.pk, member_intern.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Стажёров Детализируемый")
        self.assertContains(response, "0700111222")

    def test_cannot_view_intern_not_on_own_project(self):
        outsider = Intern.objects.create(full_name="Не в команде")
        response = self.client.get(
            reverse("pm_portal:intern_detail", args=[self.project_a.pk, outsider.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_cannot_view_via_foreign_project(self):
        """Свой стажёр, но проект в урле подделан на чужой — 404."""
        member_intern = Intern.objects.create(full_name="Стажёров Свой")
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:intern_detail", args=[self.project_b.pk, member_intern.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_left_member_not_viewable(self):
        member_intern = Intern.objects.create(full_name="Вышедший")
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT,
        )
        response = self.client.get(
            reverse("pm_portal:intern_detail", args=[self.project_a.pk, member_intern.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_team_tab_links_to_detail_for_active_members(self):
        member_intern = Intern.objects.create(full_name="Кликабельный")
        TeamMember.objects.create(
            project=self.project_a, intern=member_intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=team",
        )
        self.assertContains(
            response,
            reverse("pm_portal:intern_detail", args=[self.project_a.pk, member_intern.pk]),
        )

    def test_shows_activity_scores_from_meetings(self):
        from apps.attendance.models import GroupMeeting, MeetingKind, WorkScore
        from apps.flows.models import Flow, Group

        flow = Flow.objects.create(number=1, status=Flow.Status.ACTIVE)
        group = Group.objects.create(flow=flow, number=1, project=self.project_a)
        member_intern = Intern.objects.create(full_name="Оцениваемый Активностью")
        TeamMember.objects.create(
            project=self.project_a, group=group, intern=member_intern,
            role=TeamRole.BACKEND, status=TeamMember.Status.ACTIVE,
        )
        meeting = GroupMeeting.objects.create(
            group=group, kind=MeetingKind.INTERNAL, date=datetime.date(2026, 9, 1),
        )
        WorkScore.objects.create(meeting=meeting, intern=member_intern, score=8)

        response = self.client.get(
            reverse("pm_portal:intern_detail", args=[self.project_a.pk, member_intern.pk]),
        )
        self.assertContains(response, "Активность: 8,0")
        self.assertContains(response, "8/10")


class PmDocumentTests(PmProjectOwnershipTests):
    """Документы — загрузка и просмотр только по своему проекту."""

    def setUp(self):
        super().setUp()
        from apps.documents.models import DocumentType

        self.doc_type = DocumentType.objects.create(code="contract", name="Договор")

    def test_can_upload_document_to_own_project(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.documents.models import Document

        upload = SimpleUploadedFile("contract.txt", b"text", content_type="text/plain")
        self.client.post(
            reverse("pm_portal:document_upload", args=[self.project_a.pk]),
            {"doc_type": self.doc_type.pk, "number": "1", "status": "draft", "file": upload},
        )
        self.assertTrue(Document.objects.filter(project=self.project_a).exists())

    def test_cannot_upload_document_to_foreign_project(self):
        from apps.documents.models import Document

        response = self.client.post(
            reverse("pm_portal:document_upload", args=[self.project_b.pk]),
            {"doc_type": self.doc_type.pk, "number": "1", "status": "draft"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Document.objects.filter(project=self.project_b).exists())

    def test_document_locked_to_own_project_even_if_posted(self):
        from apps.documents.models import Document

        self.client.post(
            reverse("pm_portal:document_upload", args=[self.project_a.pk]),
            {"project": self.project_b.pk, "doc_type": self.doc_type.pk, "number": "2", "status": "draft"},
        )
        document = Document.objects.get(number="2")
        self.assertEqual(document.project, self.project_a)

    def test_documents_tab_shows_only_own_project_documents(self):
        from apps.documents.models import Document

        Document.objects.create(
            project=self.project_a, doc_type=self.doc_type, number="OWN-1",
        )
        Document.objects.create(
            project=self.project_b, doc_type=self.doc_type, number="FOREIGN-1",
        )
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=documents",
        )
        self.assertContains(response, "OWN-1")
        self.assertNotContains(response, "FOREIGN-1")

    def test_documents_tab_shows_checklist_format(self):
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=documents",
        )
        self.assertContains(response, "Обязательных загружено")
        self.assertContains(response, "Бриф заказчика")

    def test_can_approve_own_document(self):
        from apps.documents.models import Document

        document = Document.objects.create(
            project=self.project_a, doc_type=self.doc_type, number="3",
        )
        self.client.post(
            reverse("pm_portal:document_approve", args=[self.project_a.pk, document.pk]),
        )
        document.refresh_from_db()
        self.assertTrue(document.is_signed)
        self.assertEqual(document.status, "signed")

    def test_cannot_approve_document_of_foreign_project(self):
        from apps.documents.models import Document

        document = Document.objects.create(
            project=self.project_b, doc_type=self.doc_type, number="4",
        )
        response = self.client.post(
            reverse("pm_portal:document_approve", args=[self.project_a.pk, document.pk]),
        )
        self.assertEqual(response.status_code, 404)
        document.refresh_from_db()
        self.assertFalse(document.is_signed)

    def test_can_edit_own_document(self):
        from apps.documents.models import Document

        document = Document.objects.create(
            project=self.project_a, doc_type=self.doc_type, number="5",
        )
        self.client.post(
            reverse("pm_portal:document_update", args=[self.project_a.pk, document.pk]),
            {"doc_type": self.doc_type.pk, "number": "5-updated", "status": "draft"},
        )
        document.refresh_from_db()
        self.assertEqual(document.number, "5-updated")

    def test_cannot_edit_document_of_foreign_project(self):
        from apps.documents.models import Document

        document = Document.objects.create(
            project=self.project_b, doc_type=self.doc_type, number="6",
        )
        response = self.client.get(
            reverse("pm_portal:document_update", args=[self.project_a.pk, document.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_upload_link_prefills_type_from_checklist(self):
        from apps.documents import services as document_services
        from apps.documents.models import DocumentType

        document_services.ensure_default_types()
        brief = DocumentType.objects.get(code="brief")
        response = self.client.get(
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=documents",
        )
        self.assertContains(
            response,
            f"{reverse('pm_portal:document_upload', args=[self.project_a.pk])}?type={brief.pk}",
        )

    def test_can_create_brief_link_for_own_project(self):
        from apps.documents.models import ProjectBriefLink

        self.client.post(
            reverse("pm_portal:brief_link_create", args=[self.project_a.pk]),
        )
        self.assertTrue(
            ProjectBriefLink.objects.filter(
                project=self.project_a, is_active=True,
            ).exists(),
        )

    def test_cannot_create_brief_link_for_foreign_project(self):
        from apps.documents.models import ProjectBriefLink

        response = self.client.post(
            reverse("pm_portal:brief_link_create", args=[self.project_b.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ProjectBriefLink.objects.filter(project=self.project_b).exists(),
        )


class PmClientTests(PmProjectOwnershipTests):
    """Данные клиента заполняет ПМ по своему проекту."""

    def test_can_create_client_for_own_project_without_one(self):
        response = self.client.post(
            reverse("pm_portal:client_edit", args=[self.project_a.pk]),
            {
                "organization": "ОсОО Тестклиент", "contact_name": "Иванов И.",
                "phone": "0700111222", "email": "client@example.com",
                "address": "", "city": "Бишкек",
            },
        )
        self.project_a.refresh_from_db()
        self.assertIsNotNone(self.project_a.client)
        self.assertEqual(self.project_a.client.organization, "ОсОО Тестклиент")
        self.assertRedirects(
            response,
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=client",
        )

    def test_can_edit_existing_client_of_own_project(self):
        from apps.clients.models import Client

        client = Client.objects.create(organization="Старое название")
        self.project_a.client = client
        self.project_a.save(update_fields=["client"])

        self.client.post(
            reverse("pm_portal:client_edit", args=[self.project_a.pk]),
            {
                "organization": "Новое название", "contact_name": "",
                "phone": "", "email": "", "address": "", "city": "",
            },
        )
        client.refresh_from_db()
        self.assertEqual(client.organization, "Новое название")

    def test_cannot_edit_client_of_foreign_project(self):
        from apps.clients.models import Client

        client = Client.objects.create(organization="Чужой клиент")
        self.project_b.client = client
        self.project_b.save(update_fields=["client"])

        response = self.client.post(
            reverse("pm_portal:client_edit", args=[self.project_b.pk]),
            {"organization": "Взлом", "contact_name": "", "phone": "",
             "email": "", "address": "", "city": ""},
        )
        self.assertEqual(response.status_code, 404)
        client.refresh_from_db()
        self.assertEqual(client.organization, "Чужой клиент")

    def test_requisites_and_comment_not_editable_by_pm(self):
        from apps.clients.models import Client

        client = Client.objects.create(
            organization="С реквизитами", requisites="ИНН 000", comment="служебное",
        )
        self.project_a.client = client
        self.project_a.save(update_fields=["client"])

        response = self.client.get(reverse("pm_portal:client_edit", args=[self.project_a.pk]))
        self.assertNotContains(response, "requisites")
        self.assertNotContains(response, 'name="comment"')

        self.client.post(
            reverse("pm_portal:client_edit", args=[self.project_a.pk]),
            {
                "organization": "С реквизитами", "contact_name": "",
                "phone": "", "email": "", "address": "", "city": "",
            },
        )
        client.refresh_from_db()
        self.assertEqual(client.requisites, "ИНН 000")
        self.assertEqual(client.comment, "служебное")


class PmPortalExcludedActionsTests(TestCase):
    """Статус проекта, его завершение, «Проблемный» и правка карточки —
    этих действий в портале ПМ просто нет: не спрятаны, а физически
    отсутствуют в urls.py. Статусы отдельных этапов ПМ двигает сам
    (см. PmStageTests), но не через общий stage_update основного
    приложения."""

    def test_no_status_stage_or_completion_routes_exist(self):
        from django.urls import NoReverseMatch

        for name in (
            "pm_portal:stage_update", "pm_portal:project_complete",
            "pm_portal:project_update", "pm_portal:mark_problematic",
        ):
            with self.assertRaises(NoReverseMatch):
                reverse(name, args=[1])


class PmStageTests(PmProjectOwnershipTests):
    """ПМ сам двигает этапы и видит красное напоминание, пока не сверит их."""

    def setUp(self):
        super().setUp()
        from apps.projects.services import create_project

        create_project(self.project_a)
        create_project(self.project_b)
        self.project_a.refresh_from_db()
        self.stages_url = (
            reverse("pm_portal:project_detail", args=[self.project_a.pk]) + "?tab=stages"
        )

    def _stage(self, project, key):
        return project.stages.get(key=key)

    def test_alert_shown_until_checked(self):
        response = self.client.get(reverse("pm_portal:dashboard"))
        self.assertContains(response, "просит обновить этап проекта «Проект A»")
        # чужой проект в напоминаниях не светится
        self.assertNotContains(response, "«Проект B»")

    def test_alert_names_the_requester(self):
        from apps.pm_portal import stages

        response = self.client.get(reverse("pm_portal:dashboard"))
        self.assertContains(response, f"{stages.REMINDER_FROM} просит обновить этап")

    def test_setting_stage_updates_project_and_hides_alert(self):
        from apps.projects.models import ProjectStage

        stage = self._stage(self.project_a, "new")
        response = self.client.post(
            reverse("pm_portal:stage_set", args=[self.project_a.pk, stage.pk]),
            {"status": ProjectStage.Status.DONE},
        )
        self.assertRedirects(response, self.stages_url, fetch_redirect_response=False)
        stage.refresh_from_db()
        self.project_a.refresh_from_db()
        self.assertEqual(stage.status, ProjectStage.Status.DONE)
        self.assertIsNotNone(stage.end_date)
        self.assertNotEqual(self.project_a.current_stage, "new")
        self.assertGreater(self.project_a.progress, 0)
        self.assertIsNotNone(self.project_a.stages_checked_at)
        self.assertTrue(
            self.project_a.history.filter(field="Этап «Новый»", user=self.pm_user).exists()
        )
        dashboard = self.client.get(reverse("pm_portal:dashboard"))
        self.assertNotContains(dashboard, "просит обновить этап")

    def test_confirm_hides_alert_without_changes(self):
        response = self.client.post(
            reverse("pm_portal:stages_confirm", args=[self.project_a.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.project_a.refresh_from_db()
        self.assertIsNotNone(self.project_a.stages_checked_at)
        dashboard = self.client.get(reverse("pm_portal:dashboard"))
        self.assertNotContains(dashboard, "просит обновить этап")

    def test_alert_comes_back_next_day(self):
        from django.utils import timezone

        from apps.pm_portal import stages

        self.project_a.stages_checked_at = timezone.now() - datetime.timedelta(days=1)
        self.project_a.save(update_fields=["stages_checked_at"])
        self.assertTrue(stages.needs_stage_check(self.project_a))
        dashboard = self.client.get(reverse("pm_portal:dashboard"))
        self.assertContains(dashboard, "просит обновить этап проекта «Проект A»")

    def test_no_alert_for_inactive_project(self):
        from apps.pm_portal import stages
        from apps.projects.models import ProjectStatus

        self.project_a.status = ProjectStatus.COMPLETED
        self.assertFalse(stages.needs_stage_check(self.project_a))

    def test_cannot_touch_foreign_project_stage(self):
        stage = self._stage(self.project_b, "new")
        response = self.client.post(
            reverse("pm_portal:stage_set", args=[self.project_b.pk, stage.pk]),
            {"status": "done"},
        )
        self.assertEqual(response.status_code, 404)
        stage.refresh_from_db()
        self.assertEqual(stage.status, "not_started")

    def test_stage_of_other_project_rejected_via_own_url(self):
        stage = self._stage(self.project_b, "new")
        response = self.client.post(
            reverse("pm_portal:stage_set", args=[self.project_a.pk, stage.pk]),
            {"status": "done"},
        )
        self.assertEqual(response.status_code, 404)

    def test_completed_service_stage_not_editable(self):
        stage = self._stage(self.project_a, "completed")
        response = self.client.post(
            reverse("pm_portal:stage_set", args=[self.project_a.pk, stage.pk]),
            {"status": "done"},
        )
        self.assertEqual(response.status_code, 404)

    def test_invalid_status_rejected(self):
        stage = self._stage(self.project_a, "new")
        self.client.post(
            reverse("pm_portal:stage_set", args=[self.project_a.pk, stage.pk]),
            {"status": "hacked"},
        )
        stage.refresh_from_db()
        self.assertEqual(stage.status, "not_started")

    def test_get_does_not_change_stage(self):
        stage = self._stage(self.project_a, "new")
        self.client.get(
            reverse("pm_portal:stage_set", args=[self.project_a.pk, stage.pk]),
        )
        stage.refresh_from_db()
        self.assertEqual(stage.status, "not_started")

    def test_stages_tab_lists_stages_without_service_stage(self):
        response = self.client.get(self.stages_url)
        self.assertEqual(response.status_code, 200)
        keys = [stage.key for stage in response.context["stages"]]
        self.assertIn("new", keys)
        self.assertNotIn("completed", keys)

    def test_confirm_ignores_external_next(self):
        response = self.client.post(
            reverse("pm_portal:stages_confirm", args=[self.project_a.pk]),
            {"next": "https://evil.example.com/"},
        )
        self.assertEqual(response["Location"], self.stages_url)
