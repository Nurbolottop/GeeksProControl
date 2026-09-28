from unittest import mock

from django.test import TestCase

from apps.graduate_bot import services
from apps.interns.models import GraduateStatus, Intern, InternStatus, ResumeBankStatus
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

    def test_team_lead_not_found_even_with_pending_status(self):
        """Тимлид — уже сотрудник, а не выпускник: бот не должен вести его
        через сценарий стажёра, даже если graduate_status как-то выставлен."""
        lead = Intern.objects.create(
            full_name="Тимлидов Тимур", graduate_status=GraduateStatus.PENDING,
        )
        TeamMember.objects.create(
            project=self.project, intern=lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        self.assertEqual(services.find_graduates("Тимлидов"), [])


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

    def test_matches_with_parentheses_and_dots(self):
        self.assertTrue(services.phone_matches(self.intern, "+996 (501) 644.171"))

    def test_incomplete_stored_phone_still_matches_on_available_digits(self):
        """Если телефон в карточке когда-то занесли не полностью (меньше
        9 цифр), это не должно значить «никакой формат не подходит» —
        сверяем по тому, что реально есть."""
        intern = Intern.objects.create(full_name="Неполный Телефон", phone="644171")
        self.assertTrue(services.phone_matches(intern, "0501644171"))
        self.assertTrue(services.phone_matches(intern, "+996 501 644 171"))

    def test_very_short_stored_phone_does_not_match(self):
        intern = Intern.objects.create(full_name="Совсем Короткий", phone="171")
        self.assertFalse(services.phone_matches(intern, "0501644171"))

    def test_blank_stored_phone_never_matches(self):
        intern = Intern.objects.create(full_name="Без Телефона", phone="")
        self.assertFalse(services.phone_matches(intern, "0501644171"))


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

    def test_creates_notification_for_head_feed(self):
        from apps.notifications.models import Notification

        services.join_graduate_to_project(self.intern, self.project)
        notification = Notification.objects.get(
            dedup_key=f"graduate-continued:{self.intern.pk}:{self.project.pk}",
        )
        self.assertIsNone(notification.intern)
        self.assertIn("Выпускник Тестов", notification.title)
        self.assertIn("Новый проект", notification.title)


class CompletedProjectsTests(TestCase):
    def setUp(self):
        self.intern = Intern.objects.create(full_name="Выпускник Проектов")

    def test_lists_completed_project_memberships(self):
        project = Project.objects.create(name="Завершённый", status=ProjectStatus.COMPLETED)
        TeamMember.objects.create(
            project=project, intern=self.intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT,
        )
        result = services.completed_projects(self.intern)
        self.assertEqual([m.project for m in result], [project])

    def test_excludes_active_and_non_completed_projects(self):
        active = Project.objects.create(name="Активный", status=ProjectStatus.ACTIVE)
        TeamMember.objects.create(
            project=active, intern=self.intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        cancelled = Project.objects.create(name="Отменённый", status=ProjectStatus.CANCELLED)
        TeamMember.objects.create(
            project=cancelled, intern=self.intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT,
        )
        self.assertEqual(services.completed_projects(self.intern), [])


class RememberChatIdTests(TestCase):
    def test_saves_chat_id(self):
        intern = Intern.objects.create(full_name="Чат Идов")
        services.remember_chat_id(intern, 12345)
        intern.refresh_from_db()
        self.assertEqual(intern.telegram_chat_id, 12345)

    def test_noop_when_unchanged(self):
        intern = Intern.objects.create(full_name="Чат Идов", telegram_chat_id=12345)
        with mock.patch.object(Intern, "save") as save:
            services.remember_chat_id(intern, 12345)
            save.assert_not_called()


class FindByChatIdTests(TestCase):
    def test_finds_by_chat_id(self):
        intern = Intern.objects.create(full_name="Найденный", telegram_chat_id=999)
        self.assertEqual(services.find_by_chat_id(999), intern)

    def test_none_when_not_found(self):
        self.assertIsNone(services.find_by_chat_id(999))


class ResolvedStatusMessageTests(TestCase):
    def test_approved_message(self):
        intern = Intern.objects.create(
            full_name="Принятый", resume_bank_status=ResumeBankStatus.APPROVED,
        )
        self.assertIn("принято", services.resolved_status_message(intern))

    def test_revision_message_includes_comment(self):
        intern = Intern.objects.create(
            full_name="На доработке", resume_bank_status=ResumeBankStatus.REVISION,
            resume_bank_comment="Поправьте фото",
        )
        self.assertIn("Поправьте фото", services.resolved_status_message(intern))

    def test_pending_message(self):
        intern = Intern.objects.create(
            full_name="Ожидающий", resume_bank_status=ResumeBankStatus.PENDING,
        )
        self.assertIn("на проверке", services.resolved_status_message(intern))

    def test_fallback_message_for_project_join(self):
        intern = Intern.objects.create(full_name="В проекте")
        self.assertIn("продолжаете стажировку", services.resolved_status_message(intern))


class SubmitToResumeBankTests(TestCase):
    def test_sets_pending_status_and_flag(self):
        intern = Intern.objects.create(full_name="Выпускник Резюме")
        result = services.submit_to_resume_bank(intern, 777)
        intern.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(intern.in_resume_bank)
        self.assertEqual(intern.resume_bank_status, ResumeBankStatus.PENDING)
        self.assertEqual(intern.telegram_chat_id, 777)

    def test_clears_graduate_status(self):
        """Иначе find_graduates() снова находит человека после /start, и
        заявку можно переотправить бесконечно (см. test_does_not_downgrade)."""
        intern = Intern.objects.create(
            full_name="Выпускник Резюме", graduate_status=GraduateStatus.PENDING,
        )
        services.submit_to_resume_bank(intern, 777)
        intern.refresh_from_db()
        self.assertEqual(intern.graduate_status, "")

    def test_logs_to_audit(self):
        from apps.audit.models import AuditLog

        intern = Intern.objects.create(full_name="Выпускник Резюме")
        services.submit_to_resume_bank(intern, 777)
        self.assertTrue(
            AuditLog.objects.filter(
                object_type="Intern", object_id=str(intern.pk),
                action="Заявка в банк резюме отправлена",
            ).exists(),
        )

    def test_creates_notification_for_head_feed(self):
        from apps.notifications.models import Notification

        intern = Intern.objects.create(full_name="Выпускник Резюме")
        services.submit_to_resume_bank(intern, 777)
        notification = Notification.objects.get(dedup_key=f"resume-bank-submitted:{intern.pk}")
        self.assertIsNone(notification.intern)
        self.assertIn("Выпускник Резюме", notification.title)

    def test_second_submission_does_not_duplicate_open_notification(self):
        from apps.notifications.models import Notification

        intern = Intern.objects.create(
            full_name="Выпускник Резюме", resume_bank_status=ResumeBankStatus.REVISION,
        )
        services.submit_to_resume_bank(intern, 777)
        services.submit_to_resume_bank(intern, 777)
        self.assertEqual(
            Notification.objects.filter(
                dedup_key=f"resume-bank-submitted:{intern.pk}",
            ).count(),
            1,
        )

    def test_does_not_downgrade_already_approved(self):
        intern = Intern.objects.create(
            full_name="Уже принят", resume_bank_status=ResumeBankStatus.APPROVED,
        )
        result = services.submit_to_resume_bank(intern, 777)
        intern.refresh_from_db()
        self.assertFalse(result)
        self.assertEqual(intern.resume_bank_status, ResumeBankStatus.APPROVED)

    def test_allows_resubmit_from_revision(self):
        intern = Intern.objects.create(
            full_name="На доработке", resume_bank_status=ResumeBankStatus.REVISION,
            resume_bank_comment="Поправьте фото",
        )
        result = services.submit_to_resume_bank(intern, 777)
        intern.refresh_from_db()
        self.assertTrue(result)
        self.assertEqual(intern.resume_bank_status, ResumeBankStatus.PENDING)
        self.assertEqual(intern.resume_bank_comment, "")


class PhoneLockTests(TestCase):
    def test_not_locked_by_default(self):
        intern = Intern.objects.create(full_name="Незаблокированный")
        self.assertFalse(services.is_phone_locked(intern))
        self.assertEqual(services.phone_lock_minutes_left(intern), 0)

    def test_lock_sets_future_timestamp_and_blocks(self):
        intern = Intern.objects.create(full_name="Подбирающий Телефон")
        services.lock_phone_verification(intern)
        intern.refresh_from_db()
        self.assertTrue(services.is_phone_locked(intern))
        self.assertGreater(services.phone_lock_minutes_left(intern), 0)

    def test_lock_expires_in_the_past_does_not_block(self):
        from datetime import timedelta

        from django.utils import timezone

        intern = Intern.objects.create(
            full_name="Старая Блокировка",
            phone_lock_until=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(services.is_phone_locked(intern))

    def test_logs_to_audit(self):
        from apps.audit.models import AuditLog

        intern = Intern.objects.create(full_name="Подбирающий Телефон")
        services.lock_phone_verification(intern)
        self.assertTrue(
            AuditLog.objects.filter(
                object_type="Intern", object_id=str(intern.pk),
                action="Бот-выпускник: проверка телефона заблокирована",
            ).exists(),
        )


class NotifyResumeBankDecisionTests(TestCase):
    def test_does_nothing_without_chat_id(self):
        intern = Intern.objects.create(full_name="Без чата")
        with mock.patch("apps.graduate_bot.bot.bot.send_message") as send:
            services.notify_resume_bank_decision(intern, approved=True)
        send.assert_not_called()

    def test_sends_congrats_when_approved(self):
        intern = Intern.objects.create(full_name="Принятый", telegram_chat_id=42)
        with mock.patch("apps.graduate_bot.bot.bot.send_message") as send:
            services.notify_resume_bank_decision(intern, approved=True)
        send.assert_called_once()
        self.assertEqual(send.call_args[0][0], 42)
        self.assertIn("Поздравляем", send.call_args[0][1])

    def test_sends_comment_when_revision(self):
        intern = Intern.objects.create(full_name="На доработке", telegram_chat_id=42)
        with mock.patch("apps.graduate_bot.bot.bot.send_message") as send:
            services.notify_resume_bank_decision(intern, approved=False, comment="Поправьте фото")
        self.assertIn("Поправьте фото", send.call_args[0][1])

    def test_swallows_send_errors(self):
        intern = Intern.objects.create(full_name="Сбой", telegram_chat_id=42)
        with mock.patch(
            "apps.graduate_bot.bot.bot.send_message", side_effect=Exception("boom"),
        ):
            services.notify_resume_bank_decision(intern, approved=True)


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


class BotActivityTests(TestCase):
    def test_excludes_people_who_never_used_the_bot(self):
        Intern.objects.create(full_name="Не писал боту")
        self.assertEqual(services.bot_activity(), [])

    def test_pending_outcome_for_unresolved_graduate(self):
        intern = Intern.objects.create(
            full_name="Ещё выбирает", telegram_chat_id=111,
            graduate_status=GraduateStatus.PENDING,
        )
        result = services.bot_activity()
        self.assertEqual([i.pk for i in result], [intern.pk])
        self.assertEqual(result[0].bot_outcome, "pending")

    def test_resume_bank_outcome(self):
        Intern.objects.create(
            full_name="В банк резюме", telegram_chat_id=222,
            resume_bank_status=ResumeBankStatus.PENDING,
        )
        result = services.bot_activity()
        self.assertEqual(result[0].bot_outcome, "resume_bank")

    def test_continued_outcome_with_current_project(self):
        project = Project.objects.create(name="Проект Продолжения")
        intern = Intern.objects.create(full_name="Продолжил", telegram_chat_id=333)
        TeamMember.objects.create(
            project=project, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        result = services.bot_activity()
        self.assertEqual(result[0].bot_outcome, "continued")
        self.assertEqual(result[0].bot_project, project)

    def test_continued_outcome_without_current_team(self):
        """Например, потом сам ушёл с проекта — не должно падать."""
        intern = Intern.objects.create(full_name="Продолжил И Ушёл", telegram_chat_id=444)
        result = services.bot_activity()
        self.assertEqual(result[0].bot_outcome, "continued")
        self.assertIsNone(result[0].bot_project)


class ActivityListViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head4", password="x")

    def test_requires_login(self):
        from django.urls import reverse

        response = self.client.get(reverse("graduate_bot:activity"))
        self.assertNotEqual(response.status_code, 200)

    def test_shows_bot_users(self):
        from django.urls import reverse

        Intern.objects.create(
            full_name="Виден В Списке", telegram_chat_id=555,
            graduate_status=GraduateStatus.PENDING,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("graduate_bot:activity"))
        self.assertContains(response, "Виден В Списке")


class WaitingForNextInternshipTests(TestCase):
    """Свободных проектов нет — выпускник записывается в очередь кнопкой,
    и мы фиксируем, что он продолжает стажировку."""

    def setUp(self):
        self.grad = Intern.objects.create(
            full_name="Эркинбаев Нурболот", telegram_chat_id=777,
            graduate_status=GraduateStatus.PENDING,
        )

    def test_request_marks_person_as_waiting(self):
        self.assertTrue(services.request_next_internship(self.grad, 777))
        self.grad.refresh_from_db()
        self.assertEqual(self.grad.graduate_status, GraduateStatus.WAITING)

    def test_second_press_changes_nothing(self):
        services.request_next_internship(self.grad, 777)
        self.assertFalse(services.request_next_internship(self.grad, 777))

    def test_head_gets_notification(self):
        from apps.notifications.models import Notification

        services.request_next_internship(self.grad, 777)
        self.assertTrue(
            Notification.objects.filter(title__contains="Ждёт стажировку").exists()
        )

    def test_event_written_to_history(self):
        from apps.audit.models import AuditLog

        services.request_next_internship(self.grad, 777)
        self.assertTrue(
            AuditLog.objects.filter(
                object_id=str(self.grad.pk), action="Ждёт ближайшую стажировку",
            ).exists()
        )

    def test_chat_id_remembered(self):
        person = Intern.objects.create(
            full_name="Без чата", graduate_status=GraduateStatus.PENDING,
        )
        services.request_next_internship(person, 999)
        person.refresh_from_db()
        self.assertEqual(person.telegram_chat_id, 999)

    def test_start_message_tells_about_the_queue(self):
        services.request_next_internship(self.grad, 777)
        self.grad.refresh_from_db()
        text = services.resolved_status_message(self.grad)
        self.assertIn("ближайшую стажировку", text)

    def test_activity_page_shows_waiting(self):
        services.request_next_internship(self.grad, 777)
        self.grad.refresh_from_db()
        result = services.bot_activity()
        self.assertEqual(result[0].bot_outcome, "waiting")


class WaitingGraduatesPageTests(TestCase):
    """Ждущих видно в «Выпускниках»: отдельная карточка и свой статус."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(username="head", password="x")
        self.client.force_login(user)
        self.project = Project.objects.create(name="Балажан", status=ProjectStatus.COMPLETED)
        self.grad = Intern.objects.create(
            full_name="Эркинбаев Нурболот", graduate_status=GraduateStatus.WAITING,
            status=InternStatus.EMPLOYABLE,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.grad, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT,
        )

    def test_summary_counts_waiting(self):
        from django.urls import reverse

        response = self.client.get(reverse("interns:graduates"))
        self.assertEqual(response.context["total"]["waiting"], 1)
        self.assertContains(response, "Ждут проект")

    def test_list_shows_status(self):
        from django.urls import reverse

        response = self.client.get(reverse("interns:graduates") + "?status=waiting")
        self.assertContains(response, "Эркинбаев Нурболот")
        self.assertContains(response, "Ждёт проект")
