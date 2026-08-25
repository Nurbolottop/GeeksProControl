import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.clients.models import Client
from apps.projects.forms import ProjectForm
from apps.projects.models import (
    DeadlineStatus,
    Project,
    ProjectStage,
    ProjectStageKey,
    ProjectStatus,
    ProjectType,
    lifecycle_stages,
)
from apps.projects.services import calculate_deadline_status, create_project

User = get_user_model()

TODAY = datetime.date(2026, 8, 14)


def make_project(**kwargs) -> Project:
    defaults = {'name': 'Test', 'status': ProjectStatus.ACTIVE, 'progress': 50}
    defaults.update(kwargs)
    return Project(**defaults)


class DeadlineStatusTests(TestCase):
    """Статус срока (ТЗ §8, §22)."""

    def test_completed_project_has_no_deadline_status(self):
        """Проект завершён — контроль срока больше не ведётся (как у
        отменённых/приостановленных): бейдж «Срок» просто пустой."""
        project = make_project(status=ProjectStatus.COMPLETED)
        self.assertEqual(calculate_deadline_status(project, TODAY), '')

    def test_no_deadline_is_on_track(self):
        project = make_project(planned_end_date=None)
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )

    def test_overdue(self):
        project = make_project(
            planned_end_date=TODAY - datetime.timedelta(days=1),
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.OVERDUE,
        )

    def test_behind_when_deadline_close_and_low_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=2), progress=50,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.BEHIND,
        )

    def test_at_risk_when_week_left_and_low_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=6), progress=50,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.AT_RISK,
        )

    def test_on_track_with_good_progress(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=2), progress=95,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )

    def test_on_track_far_deadline(self):
        project = make_project(
            planned_end_date=TODAY + datetime.timedelta(days=60), progress=5,
        )
        self.assertEqual(
            calculate_deadline_status(project, TODAY), DeadlineStatus.ON_TRACK,
        )


class CreateProjectTests(TestCase):
    """Набор этапов зависит от типа проекта."""

    def test_web_project_gets_backend_and_frontend(self):
        web_type = ProjectType.objects.create(name='Web-сайт')
        project = make_project(project_type=web_type)
        create_project(project)
        keys = list(project.stages.order_by('order').values_list('key', flat=True))
        self.assertEqual(keys, lifecycle_stages(web_type))
        self.assertIn(ProjectStageKey.BACKEND, keys)
        self.assertIn(ProjectStageKey.FRONTEND, keys)
        self.assertNotIn(ProjectStageKey.MOBILE_DEV, keys)

    def test_mobile_project_gets_mobile_development(self):
        mobile_type = ProjectType.objects.create(name='Mobile App', is_mobile=True)
        project = make_project(project_type=mobile_type)
        create_project(project)
        keys = list(project.stages.values_list('key', flat=True))
        self.assertIn(ProjectStageKey.MOBILE_DEV, keys)
        self.assertNotIn(ProjectStageKey.FRONTEND, keys)

    def test_stage_order_puts_delivery_before_production(self):
        project = make_project()
        create_project(project)
        keys = list(project.stages.order_by('order').values_list('key', flat=True))
        self.assertLess(
            keys.index(ProjectStageKey.DELIVERY),
            keys.index(ProjectStageKey.PRODUCTION),
        )
        self.assertLess(
            keys.index(ProjectStageKey.BACKEND),
            keys.index(ProjectStageKey.STAGING),
        )

    def test_creates_history_and_code(self):
        project = make_project()
        create_project(project)
        self.assertEqual(project.history.count(), 1)
        self.assertTrue(project.code.startswith('GP-'))


class ProjectFormTests(TestCase):
    """Перенос deadline требует причину (ТЗ §21)."""

    def _form_data(self, project, **overrides):
        data = {
            'name': project.name,
            'status': project.status,
            'current_stage': project.current_stage,
            'priority': project.priority,
            'progress': project.progress,
            'planned_end_date': project.planned_end_date,
            'change_reason': '',
        }
        data.update(overrides)
        return data

    def test_deadline_change_requires_reason(self):
        project = make_project(planned_end_date=TODAY)
        create_project(project)
        form = ProjectForm(
            self._form_data(
                project,
                planned_end_date=TODAY + datetime.timedelta(days=10),
            ),
            instance=project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('change_reason', form.errors)

    def test_deadline_change_with_reason_is_valid(self):
        project = make_project(planned_end_date=TODAY)
        create_project(project)
        form = ProjectForm(
            self._form_data(
                project,
                planned_end_date=TODAY + datetime.timedelta(days=10),
                change_reason='Клиент задержал материалы',
            ),
            instance=project,
        )
        self.assertTrue(form.is_valid(), form.errors)


class AuthTests(TestCase):
    """Все внутренние страницы закрыты (ТЗ §2)."""

    def test_anonymous_redirected_to_login(self):
        for url in ['/', '/projects/', '/clients/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith('/login/'))

    def test_dashboard_opens_for_authenticated_user(self):
        User.objects.create_user(username='head', password='test12345')
        self.client.login(username='head', password='test12345')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Требует внимания')


class ClientProjectsTests(TestCase):
    def test_client_can_have_multiple_projects(self):
        client_obj = Client.objects.create(organization='Org')
        for index in range(2):
            project = make_project(name=f'P{index}', client=client_obj)
            create_project(project)
        self.assertEqual(client_obj.projects.count(), 2)


class ProjectCreationFlowTests(TestCase):
    """Порядок работы: заказчик заводится вместе с проектом, ПМ — в команде."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)

    def test_new_client_created_from_project_form(self):
        response = self.client.post(reverse("projects:create"), {
            "name": "Туризм", "new_client": "ОсОО Туризм",
            "status": "active", "current_stage": "new",
            "priority": "medium", "progress": 0,
        })
        self.assertEqual(response.status_code, 302)
        client_obj = Client.objects.get(organization="ОсОО Туризм")
        project = Project.objects.get(name="Туризм")
        self.assertEqual(project.client, client_obj)
        # После создания сразу зовём назначать команду
        self.assertTrue(response.url.endswith("?tab=team"))

    def test_existing_client_not_duplicated(self):
        Client.objects.create(organization="ОсОО Омур")
        self.client.post(reverse("projects:create"), {
            "name": "Омур", "new_client": "ОсОО Омур",
            "status": "active", "current_stage": "new",
            "priority": "medium", "progress": 0,
        })
        self.assertEqual(Client.objects.filter(organization="ОсОО Омур").count(), 1)

    def test_pm_and_leads_come_from_team(self):
        from apps.interns.models import Intern
        from apps.teams.models import TeamMember, TeamRole

        project = make_project(name="Омур")
        create_project(project)
        self.assertIsNone(project.pm)
        self.assertEqual(project.leads, [])

        pm = Intern.objects.create(full_name="Алтынай")
        lead = Intern.objects.create(full_name="Бексултан")
        TeamMember.objects.create(
            project=project, intern=pm, role=TeamRole.PROJECT_MANAGER, workload=50,
        )
        TeamMember.objects.create(
            project=project, intern=lead, role=TeamRole.TEAM_LEAD, workload=50,
        )
        project.refresh_from_db()
        self.assertEqual(project.pm, pm)
        self.assertEqual(project.leads, [lead])
        self.assertTrue(project.has_pm)

    def test_projects_without_pm_selector(self):
        from apps.projects import selectors

        project = make_project(name="Без ПМ")
        create_project(project)
        self.assertIn(project, selectors.projects_without_pm())

    def test_group_created_together_with_project(self):
        from apps.flows.models import Flow, Group

        Flow.objects.create(number=1, status=Flow.Status.ACTIVE)
        project = make_project(name="Новый")
        create_project(project)
        group = Group.objects.get(project=project)
        self.assertEqual(group.flow.number, 1)
        project.refresh_from_db()
        self.assertEqual(project.flow, group.flow)
        self.assertEqual(project.number_in_flow, group.number)

    def test_flow_created_when_none_exists(self):
        from apps.flows.models import Flow

        self.assertFalse(Flow.objects.exists())
        project = make_project(name="Первый")
        create_project(project)
        self.assertEqual(Flow.objects.count(), 1)
        self.assertIsNotNone(project.group)

    def test_groups_numbered_sequentially(self):
        first = make_project(name="Раз")
        create_project(first)
        second = make_project(name="Два")
        create_project(second)
        self.assertEqual(first.group.number, 1)
        self.assertEqual(second.group.number, 2)

    def test_create_form_has_no_links_and_dates(self):
        from apps.projects.forms import ProjectCreateForm

        fields = set(ProjectCreateForm().fields)
        self.assertNotIn("staging_url", fields)
        self.assertNotIn("planned_end_date", fields)
        self.assertNotIn("progress", fields)

    def test_new_flow_created_from_project_form(self):
        from apps.flows.models import Flow

        response = self.client.post(reverse("projects:create"), {
            "name": "Учкун", "new_flow": "2",
        })
        self.assertEqual(response.status_code, 302)
        flow = Flow.objects.get(number=2)
        project = Project.objects.get(name="Учкун")
        self.assertEqual(project.flow, flow)
        self.assertEqual(project.group.flow, flow)

    def test_existing_flow_reused(self):
        from apps.flows.models import Flow

        Flow.objects.create(number=3, status=Flow.Status.ACTIVE)
        self.client.post(reverse("projects:create"), {
            "name": "Агартуу", "new_flow": "3",
        })
        self.assertEqual(Flow.objects.filter(number=3).count(), 1)

    def test_create_form_fields(self):
        from apps.projects.forms import ProjectCreateForm

        self.assertEqual(
            set(ProjectCreateForm().fields),
            {"name", "client", "flow", "city", "project_type", "description"},
        )


class ProjectReportTests(TestCase):
    """Отчёт по проекту: одно текстовое поле, дата ставится сама."""

    def setUp(self):
        from apps.projects.models import ProjectReport

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = make_project(name="ОБА")
        create_project(self.project)
        self.model = ProjectReport

    def test_report_created_with_todays_date(self):
        from django.utils import timezone

        response = self.client.post(
            reverse("projects:report_create", args=[self.project.pk]),
            {"text": "Стадия завершения. Исправили баги, впереди презентация."},
        )
        self.assertEqual(response.status_code, 302)
        report = self.model.objects.get(project=self.project)
        self.assertEqual(report.date, timezone.localdate())
        self.assertIn("Стадия завершения", report.text)
        self.assertEqual(report.author, self.user)

    def test_empty_report_not_saved(self):
        self.client.post(
            reverse("projects:report_create", args=[self.project.pk]),
            {"text": "   "},
        )
        self.assertEqual(self.model.objects.count(), 0)

    def test_report_visible_on_tab(self):
        self.model.objects.create(project=self.project, text="Идёт тестирование")
        response = self.client.get(f"{self.project.get_absolute_url()}?tab=report")
        self.assertContains(response, "Идёт тестирование")

    def test_report_updated(self):
        report = self.model.objects.create(project=self.project, text="старое")
        self.client.post(
            reverse("projects:report_update", args=[report.pk]),
            {"text": "новое"},
        )
        report.refresh_from_db()
        self.assertEqual(report.text, "новое")

    def test_report_deleted(self):
        report = self.model.objects.create(project=self.project, text="текст")
        self.client.post(reverse("projects:report_delete", args=[report.pk]))
        self.assertFalse(self.model.objects.filter(pk=report.pk).exists())


class LastReportOnOverviewTests(TestCase):
    """Последний отчёт по проекту виден сразу на «Обзоре»."""

    def setUp(self):
        from apps.projects.models import ProjectReport

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = make_project(name="БилимОрдо")
        create_project(self.project)
        self.model = ProjectReport

    def test_no_reports_shows_placeholder(self):
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "Отчётов по проекту ещё нет")

    def test_latest_report_shown_on_overview(self):
        self.model.objects.create(project=self.project, text="старый отчёт")
        newest = self.model.objects.create(project=self.project, text="новый отчёт")
        response = self.client.get(self.project.get_absolute_url())
        self.assertEqual(response.context["last_report"], newest)
        self.assertContains(response, "новый отчёт")
        self.assertNotContains(response, "старый отчёт")

    def test_overview_links_to_full_report_tab(self):
        self.model.objects.create(project=self.project, text="текст")
        response = self.client.get(self.project.get_absolute_url())
        self.assertContains(response, "?tab=report")




class ProjectListLastReportColumnTests(TestCase):
    """В общем списке проектов виден последний отчёт по каждому."""

    def setUp(self):
        from apps.projects.models import ProjectReport

        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = make_project(name="Учкун")
        create_project(self.project)
        self.model = ProjectReport

    def test_no_report_shows_placeholder(self):
        response = self.client.get(reverse("projects:list"))
        self.assertContains(response, "Нет отчёта")

    def test_latest_report_date_shown(self):
        self.model.objects.create(project=self.project, text="старый")
        newest = self.model.objects.create(project=self.project, text="новый отчёт")
        response = self.client.get(reverse("projects:list"))
        found = [
            p for p in response.context["page"].object_list
            if p.pk == self.project.pk
        ][0]
        self.assertEqual(found.last_report, newest)

    def test_last_report_lookup_does_not_scale_per_project(self):
        """Больше проектов с отчётами не должно давать N+1 запросов."""
        from django.db import connection, reset_queries
        from django.test import override_settings

        self.model.objects.create(project=self.project, text="отчёт")

        with override_settings(DEBUG=True):
            reset_queries()
            self.client.get(reverse("projects:list"))
            baseline = len(connection.queries)

            for i in range(10):
                extra = make_project(name=f"Доп {i}")
                create_project(extra)
                self.model.objects.create(project=extra, text=f"отчёт {i}")

            reset_queries()
            self.client.get(reverse("projects:list"))
            with_more_projects = len(connection.queries)

        # N+1 добавил бы примерно по запросу на каждый новый проект (10 лишних);
        # нормальный рост от самих проектов гораздо меньше этого.
        self.assertLess(with_more_projects, baseline + 10)


class StageReopenRollsBackCurrentStageTests(TestCase):
    """Переоткрытие пройденного этапа откатывает project.current_stage.

    Раньше update_stage() (форма «Изменить») никогда не трогал
    current_stage: если уже пройденный этап вручную возвращали в
    работу, бейдж «Этап» на карточке проекта продолжал показывать
    более позднюю стадию, хотя по факту проект туда откатился.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.project = make_project(name="ОБА")
        create_project(self.project)

    def test_reopening_completed_stage_moves_project_back(self):
        from apps.projects.services import complete_stage, update_stage

        delivery = self.project.stages.get(key=ProjectStageKey.DELIVERY)
        # Все этапы до «Сдачи» уже пройдены — как в реальной жизни,
        # где этапы завершаются по порядку.
        self.project.stages.filter(order__lt=delivery.order).update(
            status=ProjectStage.Status.DONE,
        )

        complete_stage(delivery, user=self.user)
        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, ProjectStageKey.PRODUCTION)

        delivery.refresh_from_db()
        delivery.status = delivery.Status.IN_PROGRESS
        update_stage(delivery, user=self.user)

        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, ProjectStageKey.DELIVERY)

    def test_editing_a_stage_ahead_of_current_does_not_move_project(self):
        from apps.projects.services import update_stage

        production = self.project.stages.get(key=ProjectStageKey.PRODUCTION)
        production.status = production.Status.IN_PROGRESS
        update_stage(production, user=self.user)

        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, ProjectStageKey.NEW)

    def test_completing_a_stage_via_edit_form_advances_project_forward(self):
        """Этап завершили не кнопкой «Завершить», а обычным «Изменить» —
        проект всё равно должен уйти на следующий незавершённый этап."""
        from apps.projects.services import update_stage

        for key in (
            ProjectStageKey.NEW, ProjectStageKey.DOCUMENTS,
            ProjectStageKey.REQUIREMENTS, ProjectStageKey.TEAM_FORMING,
        ):
            stage = self.project.stages.get(key=key)
            stage.status = stage.Status.DONE
            update_stage(stage, user=self.user)

        self.project.refresh_from_db()
        self.assertEqual(self.project.current_stage, ProjectStageKey.DESIGN)


class ProjectDeleteTests(TestCase):
    """Удаление проекта: только POST, подтверждение кодом, запись в аудит (ТЗ §27)."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = make_project(name="Туризм")
        create_project(self.project)
        self.url = reverse("projects:delete", args=[self.project.pk])

    def test_get_does_not_delete(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_wrong_code_does_not_delete(self):
        response = self.client.post(self.url, {"confirm_code": "не тот код"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Project.objects.filter(pk=self.project.pk).exists())

    def test_delete_with_code_removes_project_and_logs(self):
        from apps.audit.models import AuditLog

        code = self.project.display_code or str(self.project.pk)
        response = self.client.post(self.url, {"confirm_code": code})
        self.assertRedirects(response, reverse("projects:list"))
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        entry = AuditLog.objects.get(
            object_type="Project", object_id=str(self.project.pk), action="deleted",
        )
        self.assertEqual(entry.user, self.user)

    def test_cascade_removes_related(self):
        from apps.projects.models import ProjectReport

        self.project.reports.create(text="отчёт", author=self.user)
        code = self.project.display_code or str(self.project.pk)
        self.client.post(self.url, {"confirm_code": code})
        self.assertEqual(ProjectReport.objects.count(), 0)


class FinishedProjectsHiddenFromAllListTests(TestCase):
    """Завершённые и отменённые проекты не выходят в общем списке —
    для них есть страницы «Завершённые» и «Отклонённые»."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.active = make_project(name="Активный")
        create_project(self.active)
        for name, status in [
            ("Завершённый", ProjectStatus.COMPLETED),
            ("Отменённый", ProjectStatus.CANCELLED),
            ("Отказ клиента", ProjectStatus.REFUSED),
        ]:
            project = make_project(name=name, status=status)
            create_project(project)

    def test_all_list_hides_finished_and_cancelled(self):
        response = self.client.get(reverse("projects:list"))
        names = [p.name for p in response.context["page"].object_list]
        self.assertEqual(names, ["Активный"])

    def test_explicit_status_filter_still_works(self):
        response = self.client.get(
            reverse("projects:list"), {"status": ProjectStatus.COMPLETED},
        )
        names = [p.name for p in response.context["page"].object_list]
        self.assertEqual(names, ["Завершённый"])

    def test_dedicated_pages_still_show_them(self):
        response = self.client.get(reverse("projects:list_completed"))
        self.assertContains(response, "Завершённый")
        response = self.client.get(reverse("projects:list_rejected"))
        self.assertContains(response, "Отменённый")
        self.assertContains(response, "Отказ клиента")


class StageBadgeColorTests(TestCase):
    """Бейдж этапа выделяется зелёным, когда проект завершён."""

    def setUp(self):
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)

    def test_completed_project_shows_green_badge_in_list(self):
        project = make_project(name="Энактус", status=ProjectStatus.COMPLETED)
        create_project(project)
        project.current_stage = ProjectStageKey.COMPLETED
        project.save(update_fields=['current_stage'])

        response = self.client.get(reverse("projects:list_completed"))
        self.assertContains(
            response, '<span class="badge badge--green">✓ Завершён</span>',
        )

    def test_active_project_keeps_blue_badge_in_list(self):
        project = make_project(name="Учкун")
        create_project(project)

        response = self.client.get(reverse("projects:list"))
        self.assertContains(
            response, '<span class="badge badge--blue">Новый</span>',
        )

    def test_completed_project_row_is_highlighted(self):
        """Мало одного бейджа — завершённый проект должен быть виден по
        всему ряду в списке, иначе теряется среди активных со схожими
        по цвету бейджами (например, красной просрочкой)."""
        project = make_project(name="Вистайл", status=ProjectStatus.COMPLETED)
        create_project(project)

        response = self.client.get(reverse("projects:list_completed"))
        self.assertContains(response, 'class="project-row--completed"')

    def test_active_project_row_is_not_highlighted(self):
        project = make_project(name="Учкун")
        create_project(project)

        response = self.client.get(reverse("projects:list"))
        self.assertNotContains(response, 'project-row--completed')

    def test_cancelled_project_row_is_highlighted_too(self):
        project = make_project(name="ВФК", status=ProjectStatus.CANCELLED)
        create_project(project)

        response = self.client.get(reverse("projects:list_rejected"))
        self.assertContains(response, 'class="project-row--cancelled"')

    def test_completed_project_deadline_column_has_no_delay_badge(self):
        """Завершённый проект больше не тянет за собой «Просрочку N дн.» —
        как и у отменённых, «Срок» просто пустой: контроль сроков окончен."""
        project = make_project(
            name="Энактус", status=ProjectStatus.COMPLETED,
            planned_end_date=datetime.date(2026, 5, 6),
            actual_end_date=datetime.date(2026, 8, 24),
        )
        create_project(project)

        response = self.client.get(reverse("projects:list_completed"))
        self.assertNotContains(response, "Просрочка")
        self.assertNotContains(response, "Сдан")
