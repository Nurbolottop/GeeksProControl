import datetime

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
    """Выпуски по направлениям — всё от дат на сегодня."""

    def setUp(self):
        self.specs = make_specializations()
        importer.apply(importer.parse(ACADEMY_MESSAGE))

    def _row(self, grid, name):
        return next(row for row in grid['rows'] if row['specialization'].name == name)

    def test_grid_columns_run_from_now_to_the_last_graduation(self):
        grid = selectors.matrix(12, today=TODAY)
        months = [column['month'] for column in grid['columns']]
        self.assertEqual(months[0], datetime.date(2026, 9, 1))
        self.assertEqual(months[-1], datetime.date(2027, 3, 1))
        self.assertEqual(len(months), 7)

    def test_grid_rows_are_directions(self):
        grid = selectors.matrix(12, today=TODAY)
        self.assertEqual(
            sorted(row['specialization'].name for row in grid['rows']),
            ['Backend', 'Frontend', 'Mobile', 'UX/UI'],
        )

    def test_cell_holds_students_graduating_that_month(self):
        grid = selectors.matrix(12, today=TODAY)
        backend = self._row(grid, 'Backend')
        september, october, november = backend['cells'][:3]
        self.assertEqual(september['students'], 8)
        self.assertEqual([g.number for g in october['groups']], ['40'])
        self.assertEqual(november['students'], 7)
        # 8 + 8 + 7 + 7 + 5 (из «5–7») + 11
        self.assertEqual(backend['students'], 46)

    def test_unknown_count_is_flagged_not_counted(self):
        grid = selectors.matrix(12, today=TODAY)
        frontend = self._row(grid, 'Frontend')
        march = frontend['cells'][6]
        self.assertEqual(march['unknown'], 1)
        self.assertEqual(march['students'], 0)
        self.assertEqual(grid['unknown'], 1)

    def test_footer_sums_each_month(self):
        grid = selectors.matrix(12, today=TODAY)
        self.assertEqual(grid['footer'][1]['students'], 12)  # октябрь: Backend 8 + UX/UI 4
        self.assertEqual(grid['students'], sum(cell['students'] for cell in grid['footer']))

    def test_horizon_cuts_later_graduations(self):
        # сентябрь–ноябрь: Frontend 43, 44 · Backend 39, 40, 41 · Design 39, 40
        self.assertEqual(selectors.matrix(3, today=TODAY)['groups'], 7)
        self.assertEqual(selectors.matrix(12, today=TODAY)['groups'], 18)

    def test_cancelled_group_is_left_out(self):
        group = TrainingGroup.objects.get(number='39', specialization=self.specs['UX/UI'])
        group.status = GroupStatus.CANCELLED
        group.save()
        ux = self._row(selectors.matrix(12, today=TODAY), 'UX/UI')
        self.assertEqual(ux['cells'][1]['groups'], [])

    def test_stage_follows_dates_without_resaving(self):
        group = TrainingGroup.objects.get(number='44', specialization=self.specs['Backend'])
        self.assertEqual(group.stage_by_dates(TODAY), GroupStatus.RECRUITING)
        self.assertEqual(group.stage_by_dates(datetime.date(2026, 10, 1)), GroupStatus.STUDYING)
        self.assertEqual(group.stage_by_dates(datetime.date(2027, 4, 1)), GroupStatus.GRADUATED)

    def test_direction_cards_list_their_groups(self):
        cards = {card['specialization'].name: card for card in selectors.directions(today=TODAY)}
        mobile = cards['Mobile']
        self.assertEqual([item['group'].number for item in mobile['items']], ['4', '5', '6'])
        self.assertEqual(mobile['studying'], 5 + 7 + 9)
        self.assertEqual(mobile['items'][0]['students'], '5 студентов')

    def test_direction_card_soon_counts_three_months(self):
        cards = {card['specialization'].name: card for card in selectors.directions(today=TODAY)}
        # до конца ноября: Design 39 (4) и 40 (6)
        self.assertEqual(cards['UX/UI']['soon'], 10)

    def test_long_graduated_groups_drop_off_the_cards(self):
        cards = {card['specialization'].name: card for card in selectors.directions(today=datetime.date(2027, 1, 20))}
        numbers = [item['group'].number for item in cards['Frontend']['items']]
        self.assertNotIn('43', numbers)       # выпустилась в сентябре — давно
        self.assertIn('45', numbers)          # выпустилась в декабре — недавно

    def test_silent_directions(self):
        Specialization.objects.create(name='DevOps')
        self.assertEqual([spec.name for spec in selectors.silent_directions()], ['DevOps'])

    def test_when_label(self):
        cards = {card['specialization'].name: card for card in selectors.directions(today=TODAY)}
        backend = {item['group'].number: item['when'] for item in cards['Backend']['items']}
        self.assertEqual(backend['39'], 'выпуск через 10 дней')
        self.assertEqual(backend['40'], 'выпуск через 6 недель')
        self.assertEqual(backend['44'], 'старт через 7 дней')
        self.assertEqual(backend['43'], 'выпуск через 5 месяцев')
        self.assertEqual(selectors.span_label(7), '7 дней')
        self.assertEqual(selectors.span_label(21), '3 недели')
        self.assertEqual(selectors.span_label(35), '5 недель')

    def test_students_label_plurals(self):
        self.assertEqual(selectors.students_label(1), '1 студент')
        self.assertEqual(selectors.students_label(4), '4 студента')
        self.assertEqual(selectors.students_label(11), '11 студентов')
        self.assertEqual(selectors.students_label(22), '22 студента')
        self.assertEqual(selectors.students_label(None), 'численность неизвестна')

    def test_academy_totals(self):
        totals = selectors.academy_totals(today=TODAY)
        self.assertEqual(totals['recruiting'], 11)
        self.assertEqual(totals['unknown'], 1)
        self.assertEqual(totals['groups'], 18)
        self.assertIsNone(totals['conversion'])


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

    def test_plan_page_is_by_direction(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        response = self.client.get(reverse('training:plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Сколько студентов выпускается')
        self.assertEqual(len(response.context['directions']), 4)

    def test_empty_academy_page_opens(self):
        response = self.client.get(reverse('training:plan'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Групп академии пока нет')

    def test_horizon_switch(self):
        importer.apply(importer.parse(ACADEMY_MESSAGE))
        response = self.client.get(reverse('training:plan'), {'months': '6'})
        self.assertEqual(response.context['months'], '6')
        response = self.client.get(reverse('training:plan'), {'months': 'мусор'})
        self.assertEqual(response.context['months'], '12')

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
