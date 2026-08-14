from decimal import Decimal

from django.test import TestCase

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
