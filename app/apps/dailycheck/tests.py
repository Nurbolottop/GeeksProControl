import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.dailycheck.models import CheckItem, CheckMark, ensure_default_items

User = get_user_model()


class DailyCheckTests(TestCase):
    """Ежедневная проверка: чек-лист по дням с отметками."""

    def setUp(self):
        self.user = User.objects.create_user(username='head', password='x')
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def test_default_items_created_on_first_visit(self):
        self.assertEqual(CheckItem.objects.count(), 0)
        response = self.client.get(reverse('dailycheck:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CheckItem.objects.exists())
        self.assertContains(response, 'Ежедневная проверка')

    def test_defaults_not_duplicated(self):
        ensure_default_items()
        count = CheckItem.objects.count()
        self.client.get(reverse('dailycheck:index'))
        self.assertEqual(CheckItem.objects.count(), count)

    def test_toggle_marks_and_unmarks_for_the_day(self):
        item = CheckItem.objects.create(title='Обойти офис')
        url = reverse('dailycheck:toggle', args=[item.pk])
        self.client.post(url, {'date': self.today.isoformat()})
        mark = CheckMark.objects.get(item=item, date=self.today)
        self.assertTrue(mark.is_done)
        self.assertEqual(mark.checked_by, self.user)

        self.client.post(url, {'date': self.today.isoformat()})
        self.assertFalse(CheckMark.objects.filter(item=item).exists())

    def test_mark_belongs_to_its_own_day(self):
        item = CheckItem.objects.create(title='Проверить просрочку')
        yesterday = self.today - datetime.timedelta(days=1)
        self.client.post(
            reverse('dailycheck:toggle', args=[item.pk]),
            {'date': yesterday.isoformat()},
        )
        self.assertTrue(CheckMark.objects.filter(date=yesterday).exists())
        response = self.client.get(reverse('dailycheck:index'))
        self.assertEqual(response.context['done'], 0)

    def test_note_saved_without_marking_done(self):
        item = CheckItem.objects.create(title='Собрания вчера')
        self.client.post(
            reverse('dailycheck:note', args=[item.pk]),
            {'date': self.today.isoformat(), 'note': 'ПМ Омура не отметил'},
        )
        mark = CheckMark.objects.get(item=item)
        self.assertEqual(mark.note, 'ПМ Омура не отметил')
        self.assertFalse(mark.is_done)

    def test_custom_item_added_and_removed(self):
        self.client.post(reverse('dailycheck:item_create'), {
            'title': 'Проверить оплату сервера', 'block': 'office',
        })
        item = CheckItem.objects.get(title='Проверить оплату сервера')
        self.client.post(reverse('dailycheck:item_delete', args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_progress_counted(self):
        first = CheckItem.objects.create(title='Раз')
        CheckItem.objects.create(title='Два')
        self.client.post(
            reverse('dailycheck:toggle', args=[first.pk]),
            {'date': self.today.isoformat()},
        )
        response = self.client.get(reverse('dailycheck:index'))
        self.assertEqual(response.context['done'], 1)
        self.assertEqual(response.context['total'], 2)
        self.assertEqual(response.context['percent'], 50)

    def test_cards_render_without_data(self):
        response = self.client.get(reverse('dailycheck:index'))
        self.assertTrue(response.context['cards'])
        self.assertContains(response, 'На что смотреть сегодня')


class ProjectDailyTests(TestCase):
    """Ежедневная проверка внутри проекта."""

    def setUp(self):
        from apps.projects.models import Project
        from apps.projects.services import create_project

        self.user = User.objects.create_user(username="pm", password="x")
        self.client.force_login(self.user)
        self.project = create_project(Project(name="Туризм"))
        self.today = timezone.localdate()

    def test_tab_opens_with_empty_list(self):
        from apps.dailycheck.models import ProjectCheckItem

        response = self.client.get(f"{self.project.get_absolute_url()}?tab=daily")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ProjectCheckItem.objects.filter(project=self.project).exists(),
        )
        self.assertContains(response, "добавьте свои")

    def test_toggle_and_untoggle(self):
        from apps.dailycheck.models import ProjectCheckItem, ProjectCheckMark

        item = ProjectCheckItem.objects.create(
            project=self.project, title="Свой пункт")
        url = reverse("dailycheck:project_toggle", args=[item.pk])
        self.client.post(url, {"date": self.today.isoformat()})
        self.assertTrue(ProjectCheckMark.objects.filter(item=item).exists())
        self.client.post(url, {"date": self.today.isoformat()})
        self.assertFalse(ProjectCheckMark.objects.filter(item=item).exists())

    def test_item_removed_only_from_this_project(self):
        from apps.dailycheck.models import ProjectCheckItem
        from apps.projects.models import Project
        from apps.projects.services import create_project

        other = create_project(Project(name="Учкун"))
        item = ProjectCheckItem.objects.create(
            project=self.project, title="Общий пункт")
        ProjectCheckItem.objects.create(project=other, title="Общий пункт")
        self.client.post(reverse("dailycheck:project_item_delete", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_active)
        self.assertTrue(ProjectCheckItem.objects.filter(
            project=other, title=item.title, is_active=True).exists())

    def test_custom_item_added_to_project(self):
        from apps.dailycheck.models import ProjectCheckItem

        self.client.post(
            reverse("dailycheck:project_item_create", args=[self.project.pk]),
            {"title": "Очередь заявок пустая"},
        )
        self.assertTrue(ProjectCheckItem.objects.filter(
            project=self.project, title="Очередь заявок пустая").exists())

    def test_tab_badge_counts_unchecked(self):
        from apps.dailycheck.models import ProjectCheckItem

        item = ProjectCheckItem.objects.create(
            project=self.project, title="Раз")
        ProjectCheckItem.objects.create(project=self.project, title="Два")
        total = ProjectCheckItem.objects.filter(project=self.project).count()
        self.client.post(
            reverse("dailycheck:project_toggle", args=[item.pk]),
            {"date": self.today.isoformat()},
        )
        response = self.client.get(self.project.get_absolute_url())
        self.assertEqual(response.context["daily_left"], total - 1)
