import datetime

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import Project, ProjectStatus
from apps.reports import weekly_form
from apps.reports.services import (
    calculate_kpi,
    generate_weekly_report,
    weekly_metrics,
    week_bounds,
)


class WeeklyReportTests(TestCase):
    """Недельный отчёт (ТЗ §24.1)."""

    def test_week_bounds(self):
        # 14.08.2026 — пятница; неделя начинается в понедельник 10.08
        start, end = week_bounds(datetime.date(2026, 8, 14))
        self.assertEqual(start, datetime.date(2026, 8, 10))
        self.assertEqual(end, datetime.date(2026, 8, 16))

    def test_generate_is_idempotent(self):
        report1 = generate_weekly_report()
        report2 = generate_weekly_report()
        self.assertEqual(report1.pk, report2.pk)

    def test_metrics_count_active_projects(self):
        Project.objects.create(name='A')
        start, _ = week_bounds(timezone.localdate())
        metrics = weekly_metrics(start)
        self.assertEqual(metrics['active_projects'], 1)


class WeeklyFormTests(TestCase):
    """Недельный отчёт по форме руководителя: период — Пн–Вс."""

    def test_week_bounds_from_any_weekday(self):
        start, end = weekly_form.week_bounds(datetime.date(2026, 8, 19))
        self.assertEqual(start, datetime.date(2026, 8, 17))
        self.assertEqual(end, datetime.date(2026, 8, 23))

    def test_only_this_week_contracts_counted(self):
        monday = datetime.date(2026, 8, 17)
        Project.objects.create(name='На неделе', contract_date=monday)
        Project.objects.create(
            name='Раньше', contract_date=monday - datetime.timedelta(days=3),
        )
        data = weekly_form.build(monday)
        self.assertEqual(data['projects']['signed_contracts'], 1)

    def test_sections_cover_all_blocks(self):
        data = weekly_form.build(datetime.date(2026, 8, 17))
        sections = weekly_form.as_sections(data)
        titles = [section['title'] for section in sections]
        self.assertIn('Проекты в разработке', titles)
        self.assertIn('Внутренние собрания', titles)
        self.assertEqual(len(sections), len(weekly_form.SECTIONS))

    def test_page_generates_report_for_week(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from apps.reports.models import WeeklyReport

        user = get_user_model().objects.create_user(username='head', password='x')
        self.client.force_login(user)
        response = self.client.post(
            reverse('reports:weekly_generate'), {'week': '2026-08-19'},
        )
        self.assertEqual(response.status_code, 302)
        report = WeeklyReport.objects.get(week_start=datetime.date(2026, 8, 17))
        self.assertIn('projects', report.data)
        detail = self.client.get(
            reverse('reports:weekly_detail', args=[report.pk]),
        )
        self.assertContains(detail, 'Проекты в разработке')


class KPITests(TestCase):
    """KPI руководителя (ТЗ §25)."""

    def test_on_time_delivery_rate(self):
        today = timezone.localdate()
        # Сдан в срок
        Project.objects.create(
            name='OnTime', status=ProjectStatus.COMPLETED,
            planned_end_date=today, actual_end_date=today,
        )
        # Сдан с задержкой 4 дня
        Project.objects.create(
            name='Late', status=ProjectStatus.COMPLETED,
            planned_end_date=today - datetime.timedelta(days=4),
            actual_end_date=today,
        )
        kpi = calculate_kpi()
        self.assertEqual(kpi['on_time_delivery_rate'], 50)
        self.assertEqual(kpi['average_delay_days'], 4)
        self.assertEqual(kpi['completed_projects'], 2)

    def test_kpi_with_no_projects(self):
        kpi = calculate_kpi()
        self.assertIsNone(kpi['on_time_delivery_rate'])
        self.assertEqual(kpi['overdue_projects'], 0)


class ErrorPagesTests(TestCase):
    """Несуществующая страница должна отдавать 404, а не 500."""

    def test_missing_page_renders_404(self):
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/no-such-page/")
        request.user = AnonymousUser()
        html = render_to_string("404.html", request=request)
        self.assertIn("Страница не найдена", html)
