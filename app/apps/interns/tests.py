from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.interns.models import Intern, InternEvaluation
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


class ReserveAndResumeBankTests(TestCase):
    """«Резерв кадров» / «Банк резюме» — включая тимлидов, в отличие от
    общего списка стажёров."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head", password="x")
        self.client.force_login(self.user)

    def test_reserve_list_shows_only_flagged(self):
        in_reserve = Intern.objects.create(full_name="В резерве", in_talent_reserve=True)
        Intern.objects.create(full_name="Не в резерве")
        response = self.client.get(reverse("interns:reserve"))
        names = [p.full_name for p in response.context["people"]]
        self.assertEqual(names, ["В резерве"])
        self.assertContains(response, "В резерве")

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
        lead = Intern.objects.create(full_name="Тимлид Резервный", in_talent_reserve=True)
        TeamMember.objects.create(
            project=project, intern=lead, role=TeamRole.TEAM_LEAD,
            status=TeamMember.Status.ACTIVE,
        )
        # В общем списке стажёров тимлида не будет
        general = self.client.get(reverse("interns:list"))
        self.assertNotContains(general, "Тимлид Резервный")
        # А в резерве кадров — будет
        reserve = self.client.get(reverse("interns:reserve"))
        self.assertContains(reserve, "Тимлид Резервный")


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


class ReserveResumeBankToggleTests(TestCase):
    """Отметки «Резерв кадров» / «Банк резюме» ставятся прямо с карточки."""

    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="head2", password="x")
        self.client.force_login(self.user)
        self.intern = Intern.objects.create(full_name="Тестов Тумблер")

    def test_toggle_reserve_flips_flag(self):
        self.client.post(reverse("interns:toggle_reserve", args=[self.intern.pk]))
        self.intern.refresh_from_db()
        self.assertTrue(self.intern.in_talent_reserve)

        self.client.post(reverse("interns:toggle_reserve", args=[self.intern.pk]))
        self.intern.refresh_from_db()
        self.assertFalse(self.intern.in_talent_reserve)

    def test_toggle_resume_bank_flips_flag(self):
        self.client.post(reverse("interns:toggle_resume_bank", args=[self.intern.pk]))
        self.intern.refresh_from_db()
        self.assertTrue(self.intern.in_resume_bank)

    def test_detail_page_shows_clickable_toggle(self):
        response = self.client.get(self.intern.get_absolute_url())
        self.assertContains(response, "+ Резерв кадров")
        self.assertContains(response, "+ Банк резюме")

        self.client.post(reverse("interns:toggle_reserve", args=[self.intern.pk]))
        response = self.client.get(self.intern.get_absolute_url())
        self.assertContains(response, "✓ Резерв кадров")
