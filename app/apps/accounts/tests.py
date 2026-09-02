from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User

Model = get_user_model()


class PMScopeMiddlewareTests(TestCase):
    """ПМ заперт в /pm/, у head/administrator ничего не меняется."""

    def setUp(self):
        self.pm = Model.objects.create_user(
            username="+996700000001", password="x", role=User.Role.PROJECT_MANAGER,
        )
        self.head = Model.objects.create_user(
            username="head", password="x", role=User.Role.HEAD,
        )

    def test_pm_redirected_away_from_admin_pages(self):
        self.client.force_login(self.pm)
        response = self.client.get(reverse("projects:list"))
        self.assertRedirects(response, reverse("pm_portal:dashboard"))

    def test_pm_can_reach_pm_portal(self):
        self.client.force_login(self.pm)
        response = self.client.get(reverse("pm_portal:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_head_unaffected_on_admin_pages(self):
        self.client.force_login(self.head)
        for name in ("projects:list", "interns:list", "teams:lead_list"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)

    def test_head_can_also_open_pm_portal(self):
        """Не заблокирован — просто middleware для head ничего не делает."""
        self.client.force_login(self.head)
        response = self.client.get(reverse("pm_portal:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_still_redirected_to_login(self):
        response = self.client.get(reverse("projects:list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/login/"))


class RoleAwareLoginTests(TestCase):
    """Логин: ПМ уходит на свой портал, остальные — как раньше."""

    def setUp(self):
        self.pm = Model.objects.create_user(
            username="+996700000002", password="secretpass", role=User.Role.PROJECT_MANAGER,
        )
        self.head = Model.objects.create_user(
            username="head2", password="secretpass", role=User.Role.HEAD,
        )

    def test_pm_login_redirects_to_pm_portal(self):
        response = self.client.post(reverse("login"), {
            "username": "+996700000002", "password": "secretpass",
        })
        self.assertRedirects(response, reverse("pm_portal:dashboard"))

    def test_head_login_redirects_to_home(self):
        response = self.client.post(reverse("login"), {
            "username": "head2", "password": "secretpass",
        })
        self.assertRedirects(response, "/")

    def test_login_form_labels_field_as_phone(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Телефон")
