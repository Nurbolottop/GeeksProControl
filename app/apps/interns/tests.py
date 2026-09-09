from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.interns.models import Intern, InternEvaluation, TalentReserveCandidate
from apps.interns.services import add_evaluation


class InternRatingTests(TestCase):
    """Средний рейтинг стажёра (ТЗ §12.1)."""

    def test_average_of_single_evaluation(self):
        intern = Intern.objects.create(full_name='Тест Тестов')
        evaluation = InternEvaluation(
            intern=intern, hard_skills=5, quality=4, speed=4,
            responsibility=5, communication=3, teamwork=4, independence=4,
        )
        add_evaluation(evaluation)
        intern.refresh_from_db()
        self.assertEqual(intern.rating, Decimal('4.14'))

    def test_average_over_multiple_evaluations(self):
        intern = Intern.objects.create(full_name='Тест Тестов')
        add_evaluation(InternEvaluation(
            intern=intern, hard_skills=5, quality=5, speed=5,
            responsibility=5, communication=5, teamwork=5, independence=5,
        ))
        add_evaluation(InternEvaluation(
            intern=intern, hard_skills=3, quality=3, speed=3,
            responsibility=3, communication=3, teamwork=3, independence=3,
        ))
        intern.refresh_from_db()
        self.assertEqual(intern.rating, Decimal('4.00'))


class LeadsHiddenFromInternListTests(TestCase):
    """Тимлиды — сотрудники, в списке стажёров их не показываем."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Балажан")
        self.lead = Intern.objects.create(full_name="Болотбеков Алишер")
        self.dev = Intern.objects.create(full_name="Капаров Улар")
        TeamMember.objects.create(
            project=self.project, intern=self.lead, role=TeamRole.TEAM_LEAD,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.dev, role=TeamRole.BACKEND,
        )

    def test_lead_not_in_list(self):
        response = self.client.get(reverse("interns:list"))
        names = [p.full_name for p in response.context["page"].object_list]
        self.assertIn("Капаров Улар", names)
        self.assertNotIn("Болотбеков Алишер", names)

    def test_lead_card_still_opens(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Болотбеков Алишер")

    def test_lead_badge_says_lead(self):
        response = self.client.get(self.lead.get_absolute_url())
        self.assertEqual(response.context["kind"], "Тимлид направления")


class InternKindBadgeTests(TestCase):
    """ПМ — тоже стажёр, а не отдельная категория (в отличие от тимлида,
    который считается сотрудником): бейдж «Кто в команде» не должен
    превращаться в отдельное «Project Manager», дублируя направление «PM»."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Балажан")
        self.pm = Intern.objects.create(full_name="Болотбекова Умутай")
        TeamMember.objects.create(
            project=self.project, intern=self.pm, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )

    def test_pm_badge_is_intern_not_project_manager(self):
        """Проверяем именно верхний бейдж «Кто в команде», а не факт
        упоминания роли — «— Project Manager» у проекта в списке ниже
        законно и должен остаться: там честно показана роль на проекте."""
        response = self.client.get(self.pm.get_absolute_url())
        self.assertEqual(response.context["kind"], "Стажёр")
        self.assertContains(
            response, '<span class="badge badge--gray">Стажёр</span>',
        )


class InternListProjectColumnTests(TestCase):
    """В общем списке стажёров видно, над каким проектом кто работает."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)

    def test_shows_current_project(self):
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        project = Project.objects.create(name="Балажан")
        intern = Intern.objects.create(full_name="Аскар Тестов")
        TeamMember.objects.create(
            project=project, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )
        response = self.client.get(reverse("interns:list"))
        self.assertContains(response, "Балажан")

    def test_no_project_shows_dash(self):
        Intern.objects.create(full_name="Без проекта Тестов")
        response = self.client.get(reverse("interns:list"))
        self.assertContains(response, "—")

    def test_left_membership_not_shown_as_current(self):
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        project = Project.objects.create(name="Завершённый проект")
        intern = Intern.objects.create(full_name="Вышел Тестов")
        TeamMember.objects.create(
            project=project, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT,
        )
        response = self.client.get(reverse("interns:list"))
        self.assertNotContains(response, "Завершённый проект")

    def test_project_lookup_does_not_scale_per_intern(self):
        """Больше стажёров с проектами не должно давать N+1 запросов."""
        from django.db import connection, reset_queries
        from django.test import override_settings

        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        project = Project.objects.create(name="Балажан")
        intern = Intern.objects.create(full_name="Аскар Тестов")
        TeamMember.objects.create(
            project=project, intern=intern, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )

        with override_settings(DEBUG=True):
            reset_queries()
            self.client.get(reverse("interns:list"))
            baseline = len(connection.queries)

            for i in range(10):
                extra_project = Project.objects.create(name=f"Проект {i}")
                extra_intern = Intern.objects.create(full_name=f"Стажёр {i}")
                TeamMember.objects.create(
                    project=extra_project, intern=extra_intern,
                    role=TeamRole.BACKEND, status=TeamMember.Status.ACTIVE,
                )

            reset_queries()
            self.client.get(reverse("interns:list"))
            with_more_interns = len(connection.queries)

        self.assertLess(with_more_interns, baseline + 10)


class GrantPMAccessTests(TestCase):
    """Выдача логина ПМу со страницы стажёра."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        self.user = get_user_model().objects.create_user(
            username="head", password="x",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Балажан")
        self.pm = Intern.objects.create(full_name="Тестов ПМ")
        self.dev = Intern.objects.create(full_name="Тестов Бэкендер")
        TeamMember.objects.create(
            project=self.project, intern=self.pm, role=TeamRole.PROJECT_MANAGER,
            status=TeamMember.Status.ACTIVE,
        )
        TeamMember.objects.create(
            project=self.project, intern=self.dev, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )

    def test_button_shown_only_for_pm(self):
        pm_page = self.client.get(self.pm.get_absolute_url())
        self.assertContains(pm_page, "Выдать доступ")
        dev_page = self.client.get(self.dev.get_absolute_url())
        self.assertNotContains(dev_page, "Выдать доступ")

    def test_granting_access_creates_linked_user(self):
        from apps.accounts.models import User

        self.client.post(reverse("interns:grant_access", args=[self.pm.pk]), {
            "username": "+996700000099", "password": "somepass123",
        })
        self.pm.refresh_from_db()
        self.assertIsNotNone(self.pm.user)
        self.assertEqual(self.pm.user.username, "+996700000099")
        self.assertEqual(self.pm.user.role, User.Role.PROJECT_MANAGER)
        self.assertTrue(self.pm.user.check_password("somepass123"))

    def test_resetting_password_keeps_same_user(self):
        self.client.post(reverse("interns:grant_access", args=[self.pm.pk]), {
            "username": "+996700000099", "password": "firstpass123",
        })
        self.pm.refresh_from_db()
        first_user_id = self.pm.user_id

        self.client.post(reverse("interns:grant_access", args=[self.pm.pk]), {
            "username": "+996700000099", "password": "secondpass123",
        })
        self.pm.refresh_from_db()
        self.assertEqual(self.pm.user_id, first_user_id)
        self.assertTrue(self.pm.user.check_password("secondpass123"))


class ResumeBankListTests(TestCase):
    """«Банк резюме» — включая тимлидов, в отличие от общего списка
    стажёров."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head", password="x")
        self.client.force_login(self.user)

    def test_resume_bank_list_shows_only_flagged(self):
        Intern.objects.create(full_name="Без резюме")
        in_bank = Intern.objects.create(full_name="С резюме", in_resume_bank=True)
        response = self.client.get(reverse("interns:resume_bank"))
        names = [p.full_name for p in response.context["people"]]
        self.assertEqual(names, ["С резюме"])

    def test_team_leads_included_unlike_general_list(self):
        from apps.projects.models import Project
        from apps.teams.models import TeamMember, TeamRole

        project = Project.objects.create(name="Балажан")
        lead = Intern.objects.create(full_name="Тимлид Резюмешный", in_resume_bank=True)
        TeamMember.objects.create(
            project=project, intern=lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        general = self.client.get(reverse("interns:list"))
        self.assertNotContains(general, "Тимлид Резюмешный")
        bank = self.client.get(reverse("interns:resume_bank"))
        self.assertContains(bank, "Тимлид Резюмешный")


class ResumeBankApplyTests(TestCase):
    """Публичная анкета «Банк резюме» — без входа в систему."""

    def test_anonymous_can_submit(self):
        response = self.client.post(reverse("resume_bank_apply"), {
            "full_name": "Новый Человек", "phone": "0700111222",
            "email": "new@example.com",
        })
        self.assertEqual(response.status_code, 200)
        intern = Intern.objects.get(phone="0700111222")
        self.assertTrue(intern.in_resume_bank)
        self.assertEqual(intern.full_name, "Новый Человек")

    def test_existing_person_by_phone_is_updated_not_duplicated(self):
        Intern.objects.create(full_name="Старое Имя", phone="0700111222")
        self.client.post(reverse("resume_bank_apply"), {
            "full_name": "Новое Имя", "phone": "0700111222",
            "email": "updated@example.com",
        })
        self.assertEqual(Intern.objects.filter(phone="0700111222").count(), 1)
        intern = Intern.objects.get(phone="0700111222")
        self.assertEqual(intern.full_name, "Новое Имя")
        self.assertTrue(intern.in_resume_bank)

    def test_phone_is_required(self):
        response = self.client.post(reverse("resume_bank_apply"), {
            "full_name": "Без Телефона",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Intern.objects.filter(full_name="Без Телефона").exists())


class ProfileApplyTests(TestCase):
    """Публичная анкета профиля стажёра — без входа в систему."""

    def test_anonymous_can_submit_full_profile(self):
        response = self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Новый Стажёр", "phone": "0700333444",
            "email": "n@example.com", "telegram": "@newintern",
            "city": "Бишкек", "branch": "Ош",
            "internship_attempt": "2",
        })
        self.assertEqual(response.status_code, 200)
        intern = Intern.objects.get(phone="0700333444")
        self.assertEqual(intern.full_name, "Новый Стажёр")
        self.assertEqual(intern.telegram, "@newintern")
        self.assertEqual(intern.branch, "Ош")
        self.assertEqual(intern.internship_attempt, 2)

    def test_existing_person_by_phone_is_updated_not_duplicated(self):
        Intern.objects.create(full_name="Старое Имя", phone="0700333444")
        self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Новое Имя", "phone": "0700333444",
            "city": "Ош", "internship_attempt": "1",
        })
        self.assertEqual(Intern.objects.filter(phone="0700333444").count(), 1)
        intern = Intern.objects.get(phone="0700333444")
        self.assertEqual(intern.full_name, "Новое Имя")
        self.assertEqual(intern.city, "Ош")

    def test_existing_person_without_phone_matched_by_full_name(self):
        """У старой карточки (только ФИО, телефон не заполнен) не должно
        появиться дубля, когда стажёр сам заполняет анкету."""
        old = Intern.objects.create(full_name="Асан Асанов")
        self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Асан Асанов", "phone": "0700555666",
            "city": "Бишкек", "internship_attempt": "1",
        })
        self.assertEqual(Intern.objects.filter(full_name="Асан Асанов").count(), 1)
        old.refresh_from_db()
        self.assertEqual(old.phone, "0700555666")
        self.assertEqual(old.city, "Бишкек")

    def test_name_match_is_case_insensitive(self):
        Intern.objects.create(full_name="асан асанов")
        self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Асан Асанов", "phone": "0700555666",
            "internship_attempt": "1",
        })
        self.assertEqual(Intern.objects.filter(phone="0700555666").count(), 1)

    def test_name_match_skipped_when_existing_record_has_a_phone(self):
        """Если у старой записи уже есть телефон, совпадение по ФИО не
        используется — не хотим случайно склеить двух разных людей."""
        Intern.objects.create(full_name="Асан Асанов", phone="0700111111")
        self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Асан Асанов", "phone": "0700555666",
            "internship_attempt": "1",
        })
        self.assertEqual(Intern.objects.filter(full_name="Асан Асанов").count(), 2)

    def test_phone_is_required(self):
        response = self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Без Телефона", "internship_attempt": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Intern.objects.filter(full_name="Без Телефона").exists())

    def test_default_internship_attempt_is_one(self):
        intern = Intern.objects.create(full_name="Дефолтный")
        self.assertEqual(intern.internship_attempt, 1)

    def test_branch_only_accepts_the_two_offices(self):
        response = self.client.post(reverse("intern_profile_apply"), {
            "full_name": "Тест Филиал", "phone": "0700999888",
            "branch": "Какой-то другой офис", "internship_attempt": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Intern.objects.filter(phone="0700999888").exists())


class ReserveResumeBankToggleTests(TestCase):
    """Карточка стажёра: «В резерв кадров» — только ссылка в отдельный
    пул (без тумблера на самом Intern); «Банк резюме» — только через
    публичную анкету, тут лишь показывается бейджем."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head2", password="x")
        self.client.force_login(self.user)
        self.intern = Intern.objects.create(full_name="Тестов Тумблер")

    def test_detail_page_links_to_reserve_create_prefilled(self):
        response = self.client.get(self.intern.get_absolute_url())
        self.assertContains(response, "+ В резерв кадров")
        self.assertContains(response, reverse("interns:reserve_create"))

    def test_resume_bank_shown_as_plain_badge_not_toggle(self):
        """Флаг банка резюме выставляется только формой — карточка его
        просто отображает, не даёт менять руками."""
        response = self.client.get(self.intern.get_absolute_url())
        self.assertNotContains(
            response, '<span class="badge badge--blue">Банк резюме</span>',
        )

        self.intern.in_resume_bank = True
        self.intern.save()
        response = self.client.get(self.intern.get_absolute_url())
        self.assertContains(response, '<span class="badge badge--blue">Банк резюме</span>')


class GraduatesListTests(TestCase):
    """«Выпускники»: стажёры, вышедшие из команды завершённого проекта."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head3", password="x")
        self.client.force_login(self.user)

    def test_shows_intern_from_completed_project_only(self):
        import datetime

        from apps.projects.models import Project, ProjectStatus
        from apps.teams.models import TeamMember, TeamRole

        finished = Project.objects.create(
            name="Завершённый", status=ProjectStatus.COMPLETED,
            actual_end_date=datetime.date(2026, 1, 15),
        )
        active = Project.objects.create(name="Активный", status=ProjectStatus.ACTIVE)

        graduate = Intern.objects.create(full_name="Выпускник Один")
        TeamMember.objects.create(
            project=finished, intern=graduate, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT, left_at=datetime.date(2026, 1, 15),
        )
        still_working = Intern.objects.create(full_name="Ещё Работает")
        TeamMember.objects.create(
            project=active, intern=still_working, role=TeamRole.BACKEND,
            status=TeamMember.Status.ACTIVE,
        )

        response = self.client.get(reverse("interns:graduates"))
        names = [p.full_name for p in response.context["people"]]
        self.assertEqual(names, ["Выпускник Один"])
        self.assertContains(response, "Завершённый")

    def test_resume_bank_read_only_and_reserve_links_out(self):
        import datetime

        from apps.projects.models import Project, ProjectStatus
        from apps.teams.models import TeamMember, TeamRole

        finished = Project.objects.create(
            name="Завершённый", status=ProjectStatus.COMPLETED,
            actual_end_date=datetime.date(2026, 1, 15),
        )
        graduate = Intern.objects.create(full_name="Выпускник Два", in_resume_bank=True)
        TeamMember.objects.create(
            project=finished, intern=graduate, role=TeamRole.BACKEND,
            status=TeamMember.Status.LEFT, left_at=datetime.date(2026, 1, 15),
        )

        response = self.client.get(reverse("interns:graduates"))
        self.assertContains(response, "В банке резюме")
        self.assertContains(response, reverse("interns:reserve_create"))


class TalentReserveStaffTests(TestCase):
    """Резерв кадров — отдельная сущность, сотрудник ведёт карточки и
    приоритет вручную."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head4", password="x")
        self.client.force_login(self.user)

    def test_create_candidate(self):
        response = self.client.post(reverse("interns:reserve_create"), {
            "full_name": "Кандидат Один", "phone": "0700123123",
            "email": "", "telegram": "", "city": "Бишкек",
            "desired_role": "Backend разработчик", "experience": "",
            "portfolio_link": "", "priority": "0", "comment": "",
        })
        self.assertTrue(
            TalentReserveCandidate.objects.filter(full_name="Кандидат Один").exists(),
        )
        self.assertRedirects(response, reverse("interns:reserve"))

    def test_create_prefills_from_query_params(self):
        response = self.client.get(
            reverse("interns:reserve_create") + "?full_name=Иван+Иванов&phone=0700000001",
        )
        self.assertContains(response, "Иван Иванов")
        self.assertContains(response, "0700000001")

    def test_update_candidate(self):
        candidate = TalentReserveCandidate.objects.create(full_name="Старое Имя")
        self.client.post(reverse("interns:reserve_update", args=[candidate.pk]), {
            "full_name": "Новое Имя", "phone": "", "email": "", "telegram": "",
            "city": "", "desired_role": "", "experience": "",
            "portfolio_link": "", "priority": "5", "comment": "",
        })
        candidate.refresh_from_db()
        self.assertEqual(candidate.full_name, "Новое Имя")
        self.assertEqual(candidate.priority, 5)

    def test_delete_candidate(self):
        candidate = TalentReserveCandidate.objects.create(full_name="Удаляемый")
        self.client.post(reverse("interns:reserve_delete", args=[candidate.pk]))
        self.assertFalse(TalentReserveCandidate.objects.filter(pk=candidate.pk).exists())

    def test_set_priority(self):
        candidate = TalentReserveCandidate.objects.create(full_name="Приоритетный")
        self.client.post(
            reverse("interns:reserve_set_priority", args=[candidate.pk]),
            {"priority": "10"},
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.priority, 10)

    def test_list_ordered_by_priority_descending(self):
        low = TalentReserveCandidate.objects.create(full_name="Низкий", priority=1)
        high = TalentReserveCandidate.objects.create(full_name="Высокий", priority=10)
        response = self.client.get(reverse("interns:reserve"))
        names = [c.full_name for c in response.context["candidates"]]
        self.assertEqual(names, ["Высокий", "Низкий"])


class TalentReserveApplyTests(TestCase):
    """Публичная анкета «Резерв кадров» — без входа в систему."""

    def test_anonymous_can_submit(self):
        response = self.client.post(reverse("talent_reserve_apply"), {
            "full_name": "Новый Кандидат", "phone": "0700444555",
            "email": "cand@example.com", "desired_role": "QA",
        })
        self.assertEqual(response.status_code, 200)
        candidate = TalentReserveCandidate.objects.get(phone="0700444555")
        self.assertEqual(candidate.full_name, "Новый Кандидат")
        self.assertEqual(candidate.desired_role, "QA")

    def test_existing_person_by_phone_is_updated_not_duplicated(self):
        TalentReserveCandidate.objects.create(
            full_name="Старое Имя", phone="0700444555",
        )
        self.client.post(reverse("talent_reserve_apply"), {
            "full_name": "Новое Имя", "phone": "0700444555",
        })
        self.assertEqual(
            TalentReserveCandidate.objects.filter(phone="0700444555").count(), 1,
        )
        candidate = TalentReserveCandidate.objects.get(phone="0700444555")
        self.assertEqual(candidate.full_name, "Новое Имя")

    def test_existing_person_without_phone_matched_by_full_name(self):
        old = TalentReserveCandidate.objects.create(full_name="Асан Асанов")
        self.client.post(reverse("talent_reserve_apply"), {
            "full_name": "Асан Асанов", "phone": "0700666777",
        })
        self.assertEqual(
            TalentReserveCandidate.objects.filter(full_name="Асан Асанов").count(), 1,
        )
        old.refresh_from_db()
        self.assertEqual(old.phone, "0700666777")

    def test_phone_is_required(self):
        response = self.client.post(reverse("talent_reserve_apply"), {
            "full_name": "Без Телефона",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            TalentReserveCandidate.objects.filter(full_name="Без Телефона").exists(),
        )

    def test_priority_and_comment_not_settable_from_public_form(self):
        """Публичная анкета не даёт кандидату выставить себе приоритет —
        это только для сотрудников."""
        from apps.interns.forms import TalentReserveApplyForm

        self.assertNotIn("priority", TalentReserveApplyForm.Meta.fields)
        self.assertNotIn("comment", TalentReserveApplyForm.Meta.fields)
