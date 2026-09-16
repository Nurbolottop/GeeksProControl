import datetime

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.training import selectors
from apps.training.models import GroupStatus, Specialization, TrainingGroup

TODAY = datetime.date(2026, 9, 16)


class AcademyPlanTests(TestCase):
    """План-график: выпуски академии по месяцам."""

    def setUp(self):
        self.backend = Specialization.objects.create(name='Backend')
        self.design = Specialization.objects.create(name='UX/UI')

    def group(self, number, end, spec=None, **extra):
        data = {
            'number': number, 'specialization': spec or self.backend,
            'end_date': end, 'students_count': 20, 'wants_internship': 10,
            'expected_interns': 8,
        }
        data.update(extra)
        return TrainingGroup.objects.create(**data)

    def test_months_start_from_the_current_one(self):
        rows = selectors.plan(3, today=TODAY)
        self.assertEqual(
            [row['month'] for row in rows],
            [datetime.date(2026, 9, 1), datetime.date(2026, 10, 1), datetime.date(2026, 11, 1)],
        )
        self.assertEqual(rows[0]['label'], 'сентябрь 2026')

    def test_group_lands_in_the_month_of_its_graduation(self):
        self.group('BE-1', datetime.date(2026, 11, 20))
        rows = selectors.plan(6, today=TODAY)
        november = rows[2]
        self.assertEqual(len(november['groups']), 1)
        self.assertEqual(november['students'], 20)
        self.assertEqual(november['wants'], 10)
        self.assertEqual(november['expected'], 8)
        self.assertEqual(rows[1]['groups'], [])

    def test_directions_add_up_within_a_month(self):
        self.group('BE-1', datetime.date(2026, 10, 5), wants_internship=6)
        self.group('BE-2', datetime.date(2026, 10, 25), wants_internship=4)
        self.group('UX-1', datetime.date(2026, 10, 10), spec=self.design, wants_internship=3)
        october = selectors.plan(3, today=TODAY)[1]
        specs = dict(october['specs'])
        self.assertEqual(specs['Backend']['wants'], 10)
        self.assertEqual(specs['UX/UI']['wants'], 3)
        self.assertEqual(october['wants'], 13)

    def test_graduated_and_cancelled_groups_are_not_planned(self):
        self.group('BE-old', datetime.date(2026, 10, 1), status=GroupStatus.GRADUATED)
        self.group('BE-no', datetime.date(2026, 10, 1), status=GroupStatus.CANCELLED)
        self.group('BE-new', datetime.date(2026, 10, 1), status=GroupStatus.RECRUITING)
        october = selectors.plan(3, today=TODAY)[1]
        self.assertEqual([g.number for g in october['groups']], ['BE-new'])

    def test_groups_beyond_the_horizon_are_left_out(self):
        self.group('BE-far', datetime.date(2027, 12, 1))
        totals = selectors.plan_totals(selectors.plan(6, today=TODAY))
        self.assertEqual(totals['groups'], 0)
        totals = selectors.plan_totals(selectors.plan(24, today=TODAY))
        self.assertEqual(totals['groups'], 1)

    def test_academy_totals_and_conversion(self):
        self.group('BE-1', datetime.date(2026, 12, 1), students_count=20, wants_internship=12)
        self.group(
            'BE-0', datetime.date(2026, 3, 1), status=GroupStatus.GRADUATED,
            students_count=20, actual_interns=5,
        )
        totals = selectors.academy_totals()
        self.assertEqual(totals['studying'], 20)
        self.assertEqual(totals['wants'], 12)
        self.assertEqual(totals['conversion'], 25)

    def test_by_specialization_compares_coming_with_free_now(self):
        self.group('BE-1', datetime.date(2026, 10, 1), wants_internship=7)
        rows = {
            str(row['specialization']): row
            for row in selectors.by_specialization(12, today=TODAY)
        }
        self.assertEqual(rows['Backend']['coming'], 7)
        self.assertEqual(rows['Backend']['free_now'], 0)
        self.assertEqual(rows['UX/UI']['coming'], 0)


class AcademyViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='head', password='pass12345')
        self.client.force_login(self.user)
        self.spec = Specialization.objects.create(name='Backend')

    def test_plan_page_opens(self):
        response = self.client.get(reverse('training:plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Учатся сейчас')

    def test_horizon_switch(self):
        response = self.client.get(reverse('training:plan'), {'months': '24'})
        self.assertEqual(len(response.context['rows']), 24)
        response = self.client.get(reverse('training:plan'), {'months': 'мусор'})
        self.assertEqual(len(response.context['rows']), 12)

    def test_create_group(self):
        self.client.post(reverse('training:group_create'), {
            'number': 'BE-14', 'specialization': self.spec.pk, 'status': 'studying',
            'start_date': '2026-06-01', 'end_date': '2026-12-01',
            'students_count': 25, 'wants_internship': 15,
            'expected_interns': 10, 'actual_interns': 0,
        })
        group = TrainingGroup.objects.get(number='BE-14')
        self.assertEqual(group.wants_internship, 15)

    def test_wants_cannot_exceed_students(self):
        response = self.client.post(reverse('training:group_create'), {
            'number': 'BE-15', 'specialization': self.spec.pk, 'status': 'studying',
            'students_count': 10, 'wants_internship': 12,
            'expected_interns': 0, 'actual_interns': 0,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TrainingGroup.objects.filter(number='BE-15').exists())

    def test_graduation_before_start_is_rejected(self):
        self.client.post(reverse('training:group_create'), {
            'number': 'BE-16', 'specialization': self.spec.pk, 'status': 'studying',
            'start_date': '2026-12-01', 'end_date': '2026-06-01',
            'students_count': 10, 'wants_internship': 0,
            'expected_interns': 0, 'actual_interns': 0,
        })
        self.assertFalse(TrainingGroup.objects.filter(number='BE-16').exists())

    def test_group_list_hides_finished_by_default(self):
        TrainingGroup.objects.create(number='LIVE', specialization=self.spec)
        TrainingGroup.objects.create(
            number='DONE', specialization=self.spec, status=GroupStatus.GRADUATED,
        )
        response = self.client.get(reverse('training:group_list'))
        numbers = [g.number for g in response.context['groups']]
        self.assertEqual(numbers, ['LIVE'])
        response = self.client.get(reverse('training:group_list'), {'status': 'graduated'})
        self.assertEqual([g.number for g in response.context['groups']], ['DONE'])

    def test_group_with_interns_is_not_deleted(self):
        from apps.interns.models import Intern

        group = TrainingGroup.objects.create(number='BE-1', specialization=self.spec)
        Intern.objects.create(full_name='Стажёр', training_group=group)
        self.client.post(reverse('training:group_delete', args=[group.pk]))
        self.assertTrue(TrainingGroup.objects.filter(pk=group.pk).exists())

    def test_old_graduations_url_leads_to_the_plan(self):
        response = self.client.get(reverse('resources:graduations'))
        self.assertRedirects(response, reverse('training:plan'))
