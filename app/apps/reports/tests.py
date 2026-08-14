import datetime

from django.test import TestCase
from django.utils import timezone

from apps.projects.models import Project, ProjectStatus
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
