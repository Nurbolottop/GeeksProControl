import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.training import importer, selectors
from apps.training.models import GroupStatus, Specialization, TrainingGroup

TODAY = datetime.date(2026, 9, 16)

# Сообщение ровно в том виде, в каком его присылает академия
ACADEMY_MESSAGE = """🎨 Design
* 39 группа — старт: 09.06.2026 · конец: 06.10.2026 — 4 студента
* 40 группа — старт: 15.07.2026 · конец: 07.11.2026 — 6 студентов
* 41 группа — старт: 14.09.2026 · конец: 04.01.2027 — 8 студентов

💻 Frontend
* 43 группа — старт: 17.03.2026 · конец: 18.09.2026 — 8 студентов
* 44 группа — старт: 11.05.2026 · конец: 05.11.2026 — 9 студентов
* 45 группа — старт: 15.06.2026 · конец: 03.12.2026 — 7 студентов
* 46 группа — старт: 21.07.2026 · конец: 08.01.2027 — 5 студентов
* 47 группа — старт: 29.08.2026 · конец: 10.02.2027 — 8 студентов
* 48 группа — старт: 28.09.2026 · конец: 11.03.2027 — количество студентов пока неизвестно

⚙️Backend
* 39 группа — старт: 25.03.2026 · конец: 26.09.2026 — 8 студентов
* 40 группа — старт: 04.05.2026 · конец: 26.10.2026 — 8 студентов
* 41 группа — старт: 06.07.2026 · конец: 20.11.2026 — 7 студентов
* 42 группа — старт: 06.07.2026 · конец: 21.12.2026 — 7 студентов
* 43 группа — старт: 19.08.2026 · конец: 03.02.2027 — 5–7 студентов
* 44 группа — старт: 23.09.2026 · конец: 10.03.2027 — 11 студентов на старте

📱Flutter
* 4 группа — старт: 15.06.2026 · конец: 10.12.2026 — 5 студентов
* 5 группа — старт: 10.08.2026 · конец: 28.01.2027 — 7 студентов
* 6 группа — старт: 15.09.2026 · конец: 05.03.2027 — 9 студентов
"""


def make_specializations():
    return {
        name: Specialization.objects.create(name=name)
        for name in ('Backend', 'Frontend', 'UX/UI', 'Mobile')
    }


def frozen_today():
    return mock.patch('django.utils.timezone.localdate', return_value=TODAY)


class AcademyImportTests(TestCase):
    """Разбор сообщения академии."""

    def setUp(self):
        self.specs = make_specializations()

    def test_whole_message_is_understood(self):
        rows = importer.parse(ACADEMY_MESSAGE)
        self.assertEqual(len(rows), 18)
        self.assertEqual([row.errors for row in rows if row.errors], [])

    def test_academy_names_map_to_our_directions(self):
        rows = importer.parse(ACADEMY_MESSAGE)
        by_header = {row.direction_name: row.specialization.name for row in rows}
        self.assertEqual(by_header['Design'], 'UX/UI')
        self.assertEqual(by_header['Flutter'], 'Mobile')
        self.assertEqual(by_header['Backend'], 'Backend')

    def test_dates_and_count(self):
        row = importer.parse(ACADEMY_MESSAGE)[0]
        self.assertEqual(row.number, '39')
        self.assertEqual(row.start_date, datetime.date(2026, 6, 9))
        self.assertEqual(row.end_date, datetime.date(2026, 10, 6))
        self.assertEqual(row.students_count, 4)
        self.assertEqual(row.students_note, '')

    def test_unknown_range_and_at_start_counts(self):
        rows = {(row.specialization.name, row.number): row for row in importer.parse(ACADEMY_MESSAGE)}
        unknown = rows[('Frontend', '48')]
        self.assertIsNone(unknown.students_count)
        self.assertIn('неизвестно', unknown.students_note)
        ranged = rows[('Backend', '43')]
        self.assertEqual(ranged.students_count, 5)
        self.assertEqual(ranged.students_note, '5–7 студентов')
        at_start = rows[('Backend', '44')]
        self.assertEqual(at_start.students_count, 11)
        self.assertEqual(at_start.students_note, '11 студентов на старте')

    def test_same_number_in_different_directions_are_different_groups(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        self.assertEqual(TrainingGroup.objects.filter(number='39').count(), 2)
        self.assertEqual(TrainingGroup.objects.count(), 18)

    def test_pasting_again_does_not_duplicate(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        rows = importer.parse(ACADEMY_MESSAGE)
        self.assertTrue(all(row.action == 'same' for row in rows))
        result = importer.apply(rows)
        self.assertEqual(result['created'], 0)
        self.assertEqual(TrainingGroup.objects.count(), 18)

    def test_updated_message_changes_dates_and_count(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        updated = ACADEMY_MESSAGE.replace(
            '* 48 группа — старт: 28.09.2026 · конец: 11.03.2027 — количество студентов пока неизвестно',
            '* 48 группа — старт: 30.09.2026 · конец: 11.03.2027 — 10 студентов',
        )
        row = next(r for r in importer.parse(updated) if r.number == '48')
        self.assertEqual(row.action, 'update')
        self.assertIn('студентов', row.changes)
        importer.apply([row])
        group = TrainingGroup.objects.get(number='48', specialization=self.specs['Frontend'])
        self.assertEqual(group.students_count, 10)
        self.assertEqual(group.start_date, datetime.date(2026, 9, 30))

    def test_unknown_direction_is_an_error_not_a_guess(self):
        rows = importer.parse('🧪 Кибербезопасность\n* 1 группа — старт: 01.09.2026 · конец: 01.03.2027 — 5 студентов')
        self.assertEqual(rows[0].action, 'error')
        self.assertIn('Кибербезопасность', rows[0].errors[0])
        importer.apply(rows)
        self.assertFalse(TrainingGroup.objects.exists())

    def test_broken_line_is_reported(self):
        rows = importer.parse('💻 Frontend\n* 49 группа — старт скоро')
        self.assertEqual(rows[0].action, 'error')


class AcademyPlanTests(TestCase):
    """План-график и сводки — всё от дат на сегодня."""

    def setUp(self):
        self.specs = make_specializations()
        with frozen_today():
            importer.apply(importer.parse(ACADEMY_MESSAGE))

    def test_months_start_from_the_current_one(self):
        rows = selectors.plan(3, today=TODAY)
        self.assertEqual(rows[0]['label'], 'сентябрь 2026')
        self.assertEqual(rows[2]['month'], datetime.date(2026, 11, 1))

    def test_group_lands_in_the_month_it_ends(self):
        october = selectors.plan(12, today=TODAY)[1]
        numbers = sorted((str(g.specialization), g.number) for g in october['groups'])
        self.assertEqual(numbers, [('Backend', '40'), ('UX/UI', '39')])
        self.assertEqual(october['students'], 12)

    def test_unknown_count_is_flagged_not_counted(self):
        march = selectors.plan(12, today=TODAY)[6]
        self.assertEqual(march['unknown'], 1)
        self.assertEqual(march['students'], 11 + 9)

    def test_horizon_cuts_later_graduations(self):
        # сентябрь–ноябрь: Frontend 43, 44 · Backend 39, 40, 41 · Design 39, 40
        self.assertEqual(selectors.plan_totals(selectors.plan(3, today=TODAY))['groups'], 7)
        self.assertEqual(selectors.plan_totals(selectors.plan(12, today=TODAY))['groups'], 18)

    def test_stage_follows_dates_without_resaving(self):
        group = TrainingGroup.objects.get(number='44', specialization=self.specs['Backend'])
        self.assertEqual(group.stage_by_dates(TODAY), GroupStatus.RECRUITING)
        self.assertEqual(group.stage_by_dates(datetime.date(2026, 10, 1)), GroupStatus.STUDYING)
        self.assertEqual(group.stage_by_dates(datetime.date(2027, 4, 1)), GroupStatus.GRADUATED)

    def test_academy_totals(self):
        totals = selectors.academy_totals(today=TODAY)
        # не стартовали на 16.09: Frontend 48 (неизвестно), Backend 44 (11)
        self.assertEqual(totals['recruiting'], 11)
        self.assertEqual(totals['unknown'], 1)
        self.assertEqual(totals['groups'], 18)
        self.assertIsNone(totals['conversion'])

    def test_cancelled_group_is_left_out(self):
        group = TrainingGroup.objects.get(number='39', specialization=self.specs['UX/UI'])
        group.status = GroupStatus.CANCELLED
        group.save()
        october = selectors.plan(12, today=TODAY)[1]
        self.assertEqual([g.number for g in october['groups']], ['40'])

    def test_by_specialization(self):
        rows = {str(r['specialization']): r for r in selectors.by_specialization(12, today=TODAY)}
        self.assertEqual(rows['Mobile']['graduating'], 5 + 7 + 9)
        self.assertEqual(rows['Mobile']['groups'], 3)
        self.assertEqual(rows['UX/UI']['graduating'], 4 + 6 + 8)


class AcademyViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='head', password='pass12345')
        self.client.force_login(self.user)
        self.specs = make_specializations()

    def test_import_shows_preview_before_saving(self):
        response = self.client.post(reverse('training:group_import'), {'text': ACADEMY_MESSAGE})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 18)
        self.assertFalse(TrainingGroup.objects.exists())

    def test_import_saves_on_confirm(self):
        response = self.client.post(
            reverse('training:group_import'), {'text': ACADEMY_MESSAGE, 'confirm': '1'},
        )
        self.assertRedirects(response, reverse('training:plan'))
        self.assertEqual(TrainingGroup.objects.count(), 18)

    def test_plan_page_hides_wants_columns_without_data(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        response = self.client.get(reverse('training:plan'))
        self.assertFalse(response.context['show_wants'])
        self.assertNotContains(response, 'Хотят на стажировку')

    def test_plan_page_shows_wants_once_entered(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        TrainingGroup.objects.filter(number='41').update(wants_internship=3)
        response = self.client.get(reverse('training:plan'), {'months': '24'})
        self.assertTrue(response.context['show_wants'])

    def test_horizon_switch(self):
        response = self.client.get(reverse('training:plan'), {'months': '24'})
        self.assertEqual(len(response.context['rows']), 24)
        response = self.client.get(reverse('training:plan'), {'months': 'мусор'})
        self.assertEqual(len(response.context['rows']), 12)

    def test_create_group_by_hand_with_unknown_count(self):
        self.client.post(reverse('training:group_create'), {
            'number': '49', 'specialization': self.specs['Frontend'].pk,
            'start_date': '2026-10-20', 'end_date': '2027-04-10',
            'students_count': '', 'students_note': 'набор идёт',
        })
        group = TrainingGroup.objects.get(number='49')
        self.assertIsNone(group.students_count)
        self.assertEqual(group.wants_internship, 0)

    def test_cancel_checkbox(self):
        group = TrainingGroup.objects.create(
            number='50', specialization=self.specs['Backend'],
            start_date=datetime.date(2026, 10, 1), end_date=datetime.date(2027, 3, 1),
        )
        payload = {
            'number': '50', 'specialization': self.specs['Backend'].pk,
            'start_date': '2026-10-01', 'end_date': '2027-03-01',
        }
        self.client.post(reverse('training:group_update', args=[group.pk]), dict(payload, cancelled='on'))
        group.refresh_from_db()
        self.assertEqual(group.status, GroupStatus.CANCELLED)
        self.client.post(reverse('training:group_update', args=[group.pk]), payload)
        group.refresh_from_db()
        self.assertNotEqual(group.status, GroupStatus.CANCELLED)

    def test_wants_cannot_exceed_students(self):
        response = self.client.post(reverse('training:group_create'), {
            'number': '51', 'specialization': self.specs['Backend'].pk,
            'students_count': 10, 'wants_internship': 12,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TrainingGroup.objects.filter(number='51').exists())

    def test_graduation_before_start_is_rejected(self):
        self.client.post(reverse('training:group_create'), {
            'number': '52', 'specialization': self.specs['Backend'].pk,
            'start_date': '2026-12-01', 'end_date': '2026-06-01',
        })
        self.assertFalse(TrainingGroup.objects.filter(number='52').exists())

    def test_group_with_interns_is_not_deleted(self):
        from apps.interns.models import Intern

        group = TrainingGroup.objects.create(number='53', specialization=self.specs['Backend'])
        Intern.objects.create(full_name='Стажёр', training_group=group)
        self.client.post(reverse('training:group_delete', args=[group.pk]))
        self.assertTrue(TrainingGroup.objects.filter(pk=group.pk).exists())

    def test_old_graduations_url_leads_to_the_plan(self):
        response = self.client.get(reverse('resources:graduations'))
        self.assertRedirects(response, reverse('training:plan'))
