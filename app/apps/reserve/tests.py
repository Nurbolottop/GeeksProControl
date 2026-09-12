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
    """Публичная анкета по ссылке."""

    def setUp(self):
        self.invite = services.issue_invite()
        self.url = self.invite.get_absolute_url()

    def test_form_opens_by_link(self):
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

    def test_link_serves_many_candidates(self):
        """Ссылка общая: каждое заполнение — отдельная карточка."""
        self.client.post(self.url, APPLICATION)
        self.client.post(self.url, dict(
            APPLICATION, full_name='Второй Кандидат', phone='0700999888',
        ))
        self.assertEqual(ReserveCandidate.objects.count(), 2)
        self.invite.refresh_from_db()
        self.assertEqual(self.invite.submissions, 2)
        self.assertTrue(self.invite.is_active)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_same_phone_updates_the_same_card(self):
        self.client.post(self.url, APPLICATION)
        self.client.post(self.url, dict(APPLICATION, city='Ош'))
        self.assertEqual(ReserveCandidate.objects.count(), 1)
        candidate = ReserveCandidate.objects.get()
        self.assertEqual(candidate.city, 'Ош')
        self.assertTrue(
            candidate.events.filter(title='Кандидат обновил свою анкету').exists(),
        )

    def test_checked_candidate_is_not_thrown_back_by_an_edit(self):
        self.client.post(self.url, APPLICATION)
        candidate = ReserveCandidate.objects.get()
        services.change_status(candidate, CandidateStatus.RESERVE)
        self.client.post(self.url, dict(APPLICATION, city='Ош'))
        candidate.refresh_from_db()
        self.assertEqual(candidate.status, CandidateStatus.RESERVE)

    def test_disabled_link_does_not_open(self):
        self.invite.deactivate()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.post(self.url, APPLICATION)
        self.assertFalse(ReserveCandidate.objects.exists())

    def test_expired_link_does_not_open(self):
        ReserveInvite.objects.filter(pk=self.invite.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_links_live_independently(self):
        second = services.issue_invite()
        self.invite.deactivate()
        second.refresh_from_db()
        self.assertTrue(second.is_active)
        self.assertEqual(self.client.get(second.get_absolute_url()).status_code, 200)

    def test_candidate_sees_no_internal_data(self):
        ReserveCandidate.objects.create(
            full_name='Оценённый', comment_pm='Внутренний комментарий',
            score_hard_skills=9, decision_comment='Секрет',
        )
        response = self.client.get(self.url)
        self.assertNotContains(response, 'Внутренний комментарий')
        self.assertNotContains(response, 'Секрет')
        self.assertNotContains(response, 'Оценённый')


class ReserveEditLinkTests(TestCase):
    """Ссылка на редактирование конкретной карточки."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='head', password='pass12345', role=User.Role.HEAD,
        )
        self.candidate = ReserveCandidate.objects.create(
            full_name='Асан Асанов', phone='0700111222', city='Бишкек',
            skills='Python', status=CandidateStatus.RESERVE,
        )

    def test_form_opens_prefilled(self):
        link = services.issue_invite(self.candidate, user=self.user)
        response = self.client.get(link.get_absolute_url())
        self.assertContains(response, 'Асан Асанов')
        self.assertContains(response, '0700111222')

    def test_edit_updates_the_same_card(self):
        link = services.issue_invite(self.candidate, user=self.user)
        self.client.post(link.get_absolute_url(), dict(
            APPLICATION, full_name='Асан Асанов', phone='0700111222', city='Ош',
        ))
        self.assertEqual(ReserveCandidate.objects.count(), 1)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.city, 'Ош')
        self.assertEqual(self.candidate.status, CandidateStatus.RESERVE)

    def test_changed_phone_does_not_split_the_card(self):
        """По ссылке на правку карточка та же, даже если сменился телефон."""
        link = services.issue_invite(self.candidate, user=self.user)
        self.client.post(link.get_absolute_url(), dict(
            APPLICATION, full_name='Асан Асанов', phone='0700555666',
        ))
        self.assertEqual(ReserveCandidate.objects.count(), 1)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.phone, '0700555666')

    def test_new_edit_link_kills_the_previous_one(self):
        first = services.issue_invite(self.candidate, user=self.user)
        services.issue_invite(self.candidate, user=self.user)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertEqual(self.client.get(first.get_absolute_url()).status_code, 404)

    def test_edit_link_is_created_from_the_card(self):
        self.client.force_login(self.user)
        self.client.post(
            reverse('reserve:edit_link', args=[self.candidate.pk]), {'ttl_days': '7'},
        )
        link = ReserveInvite.objects.get(candidate=self.candidate)
        self.assertTrue(link.is_open)
        self.assertTrue(
            self.candidate.events.filter(kind='invited').exists(),
        )

    def test_edit_links_are_not_shown_among_general_links(self):
        services.issue_invite(self.candidate, user=self.user)
        self.client.force_login(self.user)
        response = self.client.get(reverse('reserve:list'))
        self.assertEqual(response.context['open_invites'], [])

    def test_disabled_edit_link_does_not_open(self):
        link = services.issue_invite(self.candidate, user=self.user)
        link.deactivate()
        self.assertEqual(self.client.get(link.get_absolute_url()).status_code, 404)


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


class ReserveOverviewTests(TestCase):
    """Главная резерва: сводка по направлениям."""

    def setUp(self):
        from apps.training.models import Specialization

        self.user = User.objects.create_user(
            username='viewer', password='pass12345',
        )
        self.client.force_login(self.user)
        self.url = reverse('reserve:overview')
        self.backend = Specialization.objects.create(name='Backend')
        self.design = Specialization.objects.create(name='UX/UI')
        make = ReserveCandidate.objects.create
        make(full_name='Новый', specialization=self.backend, status=CandidateStatus.NEW)
        make(full_name='Проверяется', specialization=self.backend, status=CandidateStatus.REVIEW)
        make(full_name='В резерве', specialization=self.backend, status=CandidateStatus.RESERVE)
        make(full_name='На интервью', specialization=self.backend, status=CandidateStatus.INTERVIEW)
        make(full_name='С оффером', specialization=self.backend, status=CandidateStatus.OFFER)
        make(full_name='Работает', specialization=self.backend, status=CandidateStatus.EMPLOYED)
        make(full_name='Дизайнер', specialization=self.design, status=CandidateStatus.RESERVE)
        make(full_name='Ничей', specialization=None, status=CandidateStatus.RESERVE)

    def _row(self, response, key):
        return next(row for row in response.context['rows'] if row['key'] == key)

    def test_reserve_opens_on_the_summary(self):
        response = self.client.get('/reserve/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'reserve/overview.html')

    def test_counts_split_by_stage(self):
        response = self.client.get(self.url)
        row = self._row(response, str(self.backend.pk))
        self.assertEqual(row['total'], 6)
        self.assertEqual(row['new'], 2)
        self.assertEqual(row['available'], 1)
        self.assertEqual(row['in_progress'], 2)
        self.assertEqual(row['employed'], 1)

    def test_totals_sum_every_direction(self):
        totals = self.client.get(self.url).context['totals']
        self.assertEqual(totals['total'], 8)
        self.assertEqual(totals['available'], 3)

    def test_candidates_without_direction_get_their_own_row(self):
        response = self.client.get(self.url)
        row = self._row(response, 'none')
        self.assertIsNone(row['specialization'])
        self.assertEqual(row['total'], 1)
        self.assertContains(response, 'Без направления')

    def test_direction_leads_to_the_filtered_list(self):
        response = self.client.get(
            reverse('reserve:list'), {'specialization': self.backend.pk},
        )
        names = [c.full_name for c in response.context['page'].object_list]
        self.assertIn('В резерве', names)
        self.assertNotIn('Дизайнер', names)

    def test_row_without_direction_leads_to_its_own_people(self):
        response = self.client.get(
            reverse('reserve:list'), {'specialization': 'none'},
        )
        names = [c.full_name for c in response.context['page'].object_list]
        self.assertEqual(names, ['Ничей'])

    def test_archived_candidates_are_not_counted(self):
        candidate = ReserveCandidate.objects.get(full_name='Дизайнер')
        candidate.archive()
        row = self._row(self.client.get(self.url), str(self.design.pk))
        self.assertEqual(row['total'], 0)

    def test_direction_without_candidates_is_still_listed(self):
        from apps.training.models import Specialization

        Specialization.objects.create(name='DevOps')
        response = self.client.get(self.url)
        self.assertContains(response, 'DevOps')
