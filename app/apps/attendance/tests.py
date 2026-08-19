import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.attendance.models import GroupMeeting, MeetingKind, WorkScore
from apps.flows.models import Flow, Group
from apps.interns.models import Intern
from apps.projects.models import Project
from apps.teams.models import TeamMember, TeamRole

User = get_user_model()


class MeetingScoreTests(TestCase):
    """Оценка работы 0–10 за период между собраниями."""

    def setUp(self):
        self.user = User.objects.create_user(username='pm', password='x')
        self.client.force_login(self.user)
        flow = Flow.objects.create(number=1)
        project = Project.objects.create(name='Омур')
        self.group = Group.objects.create(flow=flow, number=1, project=project)
        self.person = Intern.objects.create(full_name='Зуев Мирослав')
        TeamMember.objects.create(
            group=self.group, project=project, intern=self.person,
            role=TeamRole.BACKEND, workload=50,
        )
        self.previous = GroupMeeting.objects.create(
            group=self.group, kind=MeetingKind.PM_INTERNS,
            date=datetime.date(2026, 8, 12),
        )
        self.meeting = GroupMeeting.objects.create(
            group=self.group, kind=MeetingKind.PM_INTERNS,
            date=datetime.date(2026, 8, 19),
        )

    def test_period_starts_at_previous_meeting_of_same_kind(self):
        self.assertEqual(self.meeting.period_start, self.previous.date)
        self.assertEqual(self.meeting.period_days, 7)

    def test_first_meeting_has_no_period_start(self):
        self.assertIsNone(self.previous.period_start)

    def test_other_kind_does_not_shorten_period(self):
        GroupMeeting.objects.create(
            group=self.group, kind=MeetingKind.INTERNAL,
            date=datetime.date(2026, 8, 17),
        )
        self.assertEqual(self.meeting.period_start, self.previous.date)

    def test_score_saved_and_row_returned(self):
        url = reverse('attendance:score_person', args=[self.meeting.pk])
        response = self.client.post(
            url, {'intern': self.person.pk, 'score': '8'},
        )
        self.assertEqual(response.status_code, 200)
        entry = WorkScore.objects.get(meeting=self.meeting, intern=self.person)
        self.assertEqual(entry.score, 8)
        self.assertEqual(entry.marked_by, self.user)
        self.assertEqual(self.meeting.average_score, 8)

    def test_repeat_click_clears_score(self):
        url = reverse('attendance:score_person', args=[self.meeting.pk])
        self.client.post(url, {'intern': self.person.pk, 'score': '6'})
        self.client.post(url, {'intern': self.person.pk, 'score': 'clear'})
        self.assertFalse(WorkScore.objects.filter(meeting=self.meeting).exists())

    def test_comment_kept_separately_from_score(self):
        url = reverse('attendance:score_person', args=[self.meeting.pk])
        self.client.post(url, {'intern': self.person.pk, 'score': '9'})
        self.client.post(
            url, {'intern': self.person.pk, 'comment': 'закрыл интеграцию'},
        )
        entry = WorkScore.objects.get(meeting=self.meeting, intern=self.person)
        self.assertEqual(entry.score, 9)
        self.assertEqual(entry.comment, 'закрыл интеграцию')

    def test_out_of_range_score_ignored(self):
        url = reverse('attendance:score_person', args=[self.meeting.pk])
        self.client.post(url, {'intern': self.person.pk, 'score': '15'})
        self.assertFalse(WorkScore.objects.filter(meeting=self.meeting).exists())

    def test_previous_score_and_delta_shown(self):
        WorkScore.objects.create(
            meeting=self.previous, intern=self.person, score=4,
        )
        url = reverse('attendance:score_person', args=[self.meeting.pk])
        response = self.client.post(
            url, {'intern': self.person.pk, 'score': '7'},
        )
        self.assertContains(response, 'было 4')
        self.assertContains(response, '+3')

    def test_unscored_people_listed_first(self):
        other = Intern.objects.create(full_name='Алтынай')
        TeamMember.objects.create(
            group=self.group, project=self.group.project, intern=other,
            role=TeamRole.PROJECT_MANAGER, workload=50,
        )
        WorkScore.objects.create(
            meeting=self.meeting, intern=self.person, score=9,
        )
        response = self.client.get(
            reverse('attendance:meeting_detail', args=[self.meeting.pk]),
        )
        order = [row['intern'] for row in response.context['score_rows']]
        self.assertEqual(order, [other, self.person])

    def test_detail_page_shows_both_sections(self):
        response = self.client.get(
            reverse('attendance:meeting_detail', args=[self.meeting.pk]),
        )
        self.assertContains(response, 'Кто был на собрании')
        self.assertContains(response, 'Как работал за период')
        self.assertContains(response, '12.08.2026')
