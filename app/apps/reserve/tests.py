from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.clients.models import Client as Company
from apps.interns.models import Intern
from apps.reserve import services
from apps.reserve.models import (
    CandidateStatus, RecommendationStatus, ReserveCandidate, ReserveInvite,
    ReserveRecommendation,
)
from apps.training.models import Specialization

APPLICATION = {
    'full_name': 'Тест Кандидатов',
    'phone': '0700123456',
    'city': 'Бишкек',
    'skills': 'Python, Django, PostgreSQL',
    'desired_position': 'Backend-разработчик',
    'is_looking_for_job': 'on',
    'work_format': 'remote',
    'employment_type': 'full',
    'consent_given': 'on',
}


class ReserveApplyTests(TestCase):
    """Публичная анкета по персональной ссылке."""

    def setUp(self):
        self.invite = services.issue_invite(recipient='Кандидат')
        self.url = self.invite.get_absolute_url()

    def test_form_opens_by_personal_link(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_application_without_consent_is_rejected(self):
        payload = dict(APPLICATION)
        payload.pop('consent_given')
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReserveCandidate.objects.exists())
        self.assertContains(response, 'Без согласия отправить анкету нельзя.')

    def test_application_creates_candidate_on_review(self):
        self.client.post(self.url, APPLICATION)
        candidate = ReserveCandidate.objects.get(full_name='Тест Кандидатов')
        self.assertEqual(candidate.status, CandidateStatus.REVIEW)
        self.assertTrue(candidate.consent_given)
        self.assertIsNotNone(candidate.submitted_at)
        self.assertIsNotNone(candidate.consent_at)

    def test_link_survives_the_first_submission(self):
        """Персональная ссылка живёт до своего срока: анкету можно дополнить."""
        self.client.post(self.url, APPLICATION)
        self.invite.refresh_from_db()
        self.assertTrue(self.invite.is_active)
        self.assertIsNotNone(self.invite.used_at)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_second_submission_updates_the_same_card(self):
        self.client.post(self.url, APPLICATION)
        self.client.post(self.url, dict(APPLICATION, city='Ош'))
        self.assertEqual(ReserveCandidate.objects.count(), 1)
        candidate = ReserveCandidate.objects.get()
        self.assertEqual(candidate.city, 'Ош')
        self.assertTrue(candidate.events.filter(title='Кандидат обновил свою анкету').exists())

    def test_checked_candidate_is_not_thrown_back_by_an_edit(self):
        self.client.post(self.url, APPLICATION)
        candidate = ReserveCandidate.objects.get()
        services.change_status(candidate, CandidateStatus.RESERVE)
        self.client.post(self.url, dict(APPLICATION, city='Ош'))
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.RESERVE)

    def test_expired_link_does_not_open(self):
        ReserveInvite.objects.filter(pk=self.invite.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_invite_for_existing_candidate_updates_the_same_card(self):
        candidate = ReserveCandidate.objects.create(full_name='Старое Имя')
        invite = services.issue_invite(candidate)
        self.client.post(invite.get_absolute_url(), APPLICATION)
        self.assertEqual(ReserveCandidate.objects.count(), 1)
        candidate.refresh_from_db()
        self.assertEqual(candidate.full_name, 'Тест Кандидатов')

    def test_candidate_sees_no_internal_data(self):
        candidate = ReserveCandidate.objects.create(
            full_name='Оценённый', comment_pm='Внутренний комментарий',
            score_hard_skills=9, decision_comment='Секрет',
        )
        services.recalculate_rating(candidate)
        invite = services.issue_invite(candidate)
        response = self.client.get(invite.get_absolute_url())
        self.assertNotContains(response, 'Внутренний комментарий')
        self.assertNotContains(response, 'Секрет')

    def test_new_invite_kills_the_previous_one_for_the_candidate(self):
        candidate = ReserveCandidate.objects.create(full_name='Кандидат')
        first = services.issue_invite(candidate)
        services.issue_invite(candidate)
        first.refresh_from_db()
        self.assertFalse(first.is_active)


class ReserveRatingTests(TestCase):
    """Общий рейтинг считается сам по выставленным критериям."""

    def test_rating_is_average_of_filled_scores(self):
        candidate = ReserveCandidate.objects.create(
            full_name='Оценка', score_hard_skills=8, score_quality=9,
        )
        services.recalculate_rating(candidate)
        self.assertEqual(str(candidate.rating), '8.50')

    def test_rating_is_empty_without_scores(self):
        candidate = ReserveCandidate.objects.create(full_name='Без оценок')
        services.recalculate_rating(candidate)
        self.assertIsNone(candidate.rating)


class ReservePermissionTests(TestCase):
    """Внутренние данные меняют только руководитель и администратор."""

    def setUp(self):
        self.candidate = ReserveCandidate.objects.create(full_name='Кандидат')
        self.lead = User.objects.create_user(
            username='lead', password='pass12345', role=User.Role.TEAM_LEAD,
        )
        self.head = User.objects.create_user(
            username='head', password='pass12345', role=User.Role.HEAD,
        )

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse('reserve:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_team_lead_can_view_but_not_change(self):
        self.client.force_login(self.lead)
        self.assertEqual(self.client.get(reverse('reserve:list')).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('reserve:detail', args=[self.candidate.pk])).status_code,
            200,
        )
        response = self.client.post(
            reverse('reserve:status', args=[self.candidate.pk]),
            {'status': CandidateStatus.RESERVE},
        )
        self.assertEqual(response.status_code, 403)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.NEW)

    def test_head_can_change_status(self):
        self.client.force_login(self.head)
        self.client.post(
            reverse('reserve:status', args=[self.candidate.pk]),
            {'status': CandidateStatus.RESERVE, 'comment': 'Проверен'},
        )
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, CandidateStatus.RESERVE)
        self.assertTrue(
            self.candidate.events.filter(title__contains='Статус').exists(),
        )


class ReserveFlowTests(TestCase):
    """Полный сценарий: анкета → проверка → резерв → рекомендация → оффер."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='head', password='pass12345', role=User.Role.HEAD,
        )
        self.client.force_login(self.user)
        self.company = Company.objects.create(organization='ООО Работодатель')

    def _candidate(self):
        invite = services.issue_invite(user=self.user)
        self.client.post(invite.get_absolute_url(), APPLICATION)
        return ReserveCandidate.objects.get(full_name='Тест Кандидатов')

    def test_evaluation_sets_rating_and_history(self):
        candidate = self._candidate()
        self.client.post(reverse('reserve:evaluate', args=[candidate.pk]), {
            'score_hard_skills': 8, 'score_quality': 9, 'score_independence': 8,
            'score_responsibility': 9, 'score_deadlines': 8,
            'score_communication': 9, 'score_teamwork': 8, 'score_learning': 9,
            'geekspro_level': 'junior_plus', 'decision': 'recommend',
        })
        candidate.refresh_from_db()
        self.assertEqual(str(candidate.rating), '8.50')
        self.assertEqual(candidate.geekspro_level, 'junior_plus')
        self.assertTrue(candidate.events.filter(kind='evaluated').exists())

    def test_recommendation_moves_candidate_through_statuses(self):
        candidate = self._candidate()
        services.change_status(candidate, CandidateStatus.RESERVE, user=self.user)
        self.client.post(reverse('reserve:recommend', args=[candidate.pk]), {
            'company': self.company.pk, 'vacancy': 'Junior Backend',
            'sent_on': timezone.localdate().isoformat(),
            'status': RecommendationStatus.SENT, 'comment': 'Отправили резюме',
        })
        recommendation = ReserveRecommendation.objects.get(candidate=candidate)
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.PROPOSED)

        for status, expected in [
            (RecommendationStatus.INTERVIEW, CandidateStatus.INTERVIEW),
            (RecommendationStatus.OFFER, CandidateStatus.OFFER),
            (RecommendationStatus.HIRED, CandidateStatus.EMPLOYED),
        ]:
            self.client.post(
                reverse('reserve:recommendation_status', args=[recommendation.pk]),
                {'status': status},
            )
            candidate.refresh_from_db()
            self.assertEqual(candidate.status, expected)

        # история не теряется при смене статусов
        self.assertGreaterEqual(candidate.events.count(), 8)
        self.assertEqual(candidate.recommendations_count, 1)

    def test_company_rejection_returns_candidate_to_reserve(self):
        candidate = self._candidate()
        recommendation = ReserveRecommendation.objects.create(
            candidate=candidate, company=self.company,
            sent_on=timezone.localdate(), status=RecommendationStatus.SENT,
        )
        services.change_status(candidate, CandidateStatus.PROPOSED, user=self.user)
        self.client.post(
            reverse('reserve:recommendation_status', args=[recommendation.pk]),
            {'status': RecommendationStatus.COMPANY_REJECT},
        )
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.RESERVE)

    def test_recommendation_requires_a_company(self):
        candidate = self._candidate()
        response = self.client.post(reverse('reserve:recommend', args=[candidate.pk]), {
            'vacancy': 'Junior Backend', 'sent_on': timezone.localdate().isoformat(),
            'status': RecommendationStatus.SENT,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ReserveRecommendation.objects.exists())


class ReserveListTests(TestCase):
    """Поиск, фильтры и сортировка списка."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='head', password='pass12345', role=User.Role.HEAD,
        )
        self.client.force_login(self.user)
        backend = Specialization.objects.create(name='Backend')
        design = Specialization.objects.create(name='UX/UI')
        self.first = ReserveCandidate.objects.create(
            full_name='Асан Асанов', specialization=backend, city='Бишкек',
            skills='Python, Django', rating=9, geekspro_level='middle',
            status=CandidateStatus.RESERVE, is_looking_for_job=True,
        )
        self.second = ReserveCandidate.objects.create(
            full_name='Бермет Бекова', specialization=design, city='Ош',
            skills='Figma', rating=7, geekspro_level='junior',
            status=CandidateStatus.EMPLOYED, is_looking_for_job=False,
        )

    def test_search_by_name(self):
        response = self.client.get(reverse('reserve:list'), {'q': 'Бермет'})
        self.assertContains(response, 'Бермет Бекова')
        self.assertNotContains(response, 'Асан Асанов')

    def test_filter_by_skill_and_city(self):
        response = self.client.get(reverse('reserve:list'), {'skill': 'Django'})
        self.assertContains(response, 'Асан Асанов')
        self.assertNotContains(response, 'Бермет Бекова')
        response = self.client.get(reverse('reserve:list'), {'city': 'Ош'})
        self.assertContains(response, 'Бермет Бекова')
        self.assertNotContains(response, 'Асан Асанов')

    def test_filter_by_rating_status_and_readiness(self):
        response = self.client.get(reverse('reserve:list'), {'rating': '8'})
        self.assertContains(response, 'Асан Асанов')
        self.assertNotContains(response, 'Бермет Бекова')
        response = self.client.get(
            reverse('reserve:list'), {'status': CandidateStatus.EMPLOYED},
        )
        self.assertContains(response, 'Бермет Бекова')
        response = self.client.get(reverse('reserve:list'), {'readiness': 'looking'})
        self.assertContains(response, 'Асан Асанов')
        self.assertNotContains(response, 'Бермет Бекова')

    def test_sorting_by_name_and_rating(self):
        by_rating, _ = self.client.get(reverse('reserve:list')).context['page'], None
        self.assertEqual(list(by_rating)[0], self.first)
        by_name = self.client.get(reverse('reserve:list'), {'sort': 'name'}).context['page']
        self.assertEqual(list(by_name)[0], self.first)


class ReserveFromInternTests(TestCase):
    """Кандидат из карточки стажёра — данные не перепечатываются."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='head', password='pass12345', role=User.Role.HEAD,
        )
        self.client.force_login(self.user)
        self.spec = Specialization.objects.create(name='Backend')
        self.intern = Intern.objects.create(
            full_name='Стажёр Стажёров', phone='0700999111',
            city='Бишкек', specialization=self.spec,
        )

    def test_candidate_inherits_intern_data(self):
        self.client.post(reverse('reserve:from_intern'), {'intern': self.intern.pk})
        candidate = ReserveCandidate.objects.get(intern=self.intern)
        self.assertEqual(candidate.full_name, 'Стажёр Стажёров')
        self.assertEqual(candidate.phone, '0700999111')
        self.assertEqual(candidate.specialization, self.spec)
        self.assertTrue(candidate.events.filter(kind='created').exists())

    def test_same_intern_is_not_duplicated(self):
        self.client.post(reverse('reserve:from_intern'), {'intern': self.intern.pk})
        self.client.post(reverse('reserve:from_intern'), {'intern': self.intern.pk})
        self.assertEqual(ReserveCandidate.objects.filter(intern=self.intern).count(), 1)
