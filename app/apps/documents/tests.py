from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.documents import services
from apps.documents.models import (
    BRIEF,
    CONTRACT,
    ACCEPTANCE_ACT,
    Document,
    DocumentStatus,
    DocumentTemplate,
    DocumentType,
    REQUIREMENTS,
)
from apps.projects.models import Project


class DocumentProgressTests(TestCase):
    """Контроль комплекта документов (ТЗ §17.1)."""

    def setUp(self):
        services.ensure_default_types()
        self.project = Project.objects.create(name='Test')

    def _add(self, code, **kwargs):
        return Document.objects.create(
            project=self.project,
            doc_type=DocumentType.objects.get(code=code),
            **kwargs,
        )

    def test_progress_counts_required_documents(self):
        progress = services.document_progress(self.project)
        self.assertEqual(progress['done'], 0)
        # бриф, договор, ТЗ, акт приёма-передачи
        self.assertEqual(progress['total'], 4)

        self._add(CONTRACT)
        progress = services.document_progress(self.project)
        self.assertEqual(progress['done'], 1)
        missing_codes = {t.code for t in progress['missing']}
        self.assertEqual(missing_codes, {BRIEF, REQUIREMENTS, ACCEPTANCE_ACT})

    def test_cancelled_document_not_counted(self):
        self._add(CONTRACT, status=DocumentStatus.CANCELLED)
        progress = services.document_progress(self.project)
        self.assertEqual(progress['done'], 0)

    def test_signed_check(self):
        self._add(ACCEPTANCE_ACT)
        self.assertFalse(services.has_signed_document(self.project, ACCEPTANCE_ACT))
        self.project.documents.update(is_signed=True)
        self.assertTrue(services.has_signed_document(self.project, ACCEPTANCE_ACT))


class DocumentTemplateTests(TestCase):
    """Шаблоны документов — второй раздел страницы «Документы», не
    привязаны к проекту (заготовка, которую ПМ берёт за основу)."""

    def setUp(self):
        services.ensure_default_types()
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.contract_type = DocumentType.objects.get(code=CONTRACT)

    def test_list_page_shows_both_tabs(self):
        response = self.client.get(reverse("documents:list"))
        self.assertContains(response, "Документы проектов")
        self.assertContains(response, "Шаблоны")

    def test_template_list_does_not_require_a_project(self):
        response = self.client.get(reverse("documents:templates"))
        self.assertEqual(response.status_code, 200)

    def test_create_template_without_project(self):
        upload = SimpleUploadedFile(
            "contract_template.txt", b"template text", content_type="text/plain",
        )
        response = self.client.post(reverse("documents:template_create"), {
            "doc_type": self.contract_type.pk,
            "name": "Типовой договор",
            "file": upload,
            "comment": "",
        })
        self.assertRedirects(response, reverse("documents:templates"))
        template = DocumentTemplate.objects.get(name="Типовой договор")
        self.assertEqual(template.doc_type, self.contract_type)
        self.assertEqual(template.uploaded_by, self.user)

    def test_template_shown_in_list(self):
        DocumentTemplate.objects.create(
            doc_type=self.contract_type, name="Договор v2",
        )
        response = self.client.get(reverse("documents:templates"))
        self.assertContains(response, "Договор v2")

    def test_update_template(self):
        template = DocumentTemplate.objects.create(
            doc_type=self.contract_type, name="Старое название",
            file=SimpleUploadedFile("old.txt", b"old", content_type="text/plain"),
        )
        self.client.post(
            reverse("documents:template_update", args=[template.pk]),
            {
                "doc_type": self.contract_type.pk,
                "name": "Новое название",
                "comment": "",
            },
        )
        template.refresh_from_db()
        self.assertEqual(template.name, "Новое название")

    def test_delete_template(self):
        template = DocumentTemplate.objects.create(
            doc_type=self.contract_type, name="На удаление",
        )
        self.client.post(reverse("documents:template_delete", args=[template.pk]))
        self.assertFalse(DocumentTemplate.objects.filter(pk=template.pk).exists())

    def test_rejects_disallowed_extension(self):
        upload = SimpleUploadedFile(
            "template.exe", b"binary", content_type="application/octet-stream",
        )
        self.client.post(reverse("documents:template_create"), {
            "doc_type": self.contract_type.pk, "name": "Плохой файл",
            "file": upload,
        })
        self.assertFalse(
            DocumentTemplate.objects.filter(name="Плохой файл").exists(),
        )


class ProjectBriefTests(TestCase):
    """Бриф по ссылке: ПМ выпускает ссылку под проект, заказчик
    заполняет без входа — контакты уходят в Client, остальное в
    ProjectBrief, плюс заводится Document(doc_type=brief)."""

    def setUp(self):
        from apps.documents.models import ProjectBriefLink

        services.ensure_default_types()
        self.user = User.objects.create_user(username="head", password="x")
        self.client.force_login(self.user)
        self.project = Project.objects.create(name="Бриф-проект")
        self.link_model = ProjectBriefLink

    def _payload(self, **overrides):
        data = {
            "organization": "ООО Ромашка", "contact_name": "Иван Иванов",
            "phone": "0700111222", "email": "ivan@example.com",
            "about_business": "Продаём цветы", "goal": "Интернет-магазин",
            "target_audience": "Женщины 20-45", "required_features": "Каталог, корзина",
            "references": "example.com", "deadline_wish": "2 месяца",
            "existing_site_url": "Нет", "domain": "romashka.kg",
            "integrations": "Оплата картой", "languages": "Русский, кыргызский",
            "content_owner": "Мы сами", "social_links": "instagram.com/romashka",
        }
        data.update(overrides)
        return data

    def test_issue_link_deactivates_previous(self):
        first = services.issue_brief_link(self.project, user=self.user)
        second = services.issue_brief_link(self.project, user=self.user)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(services.active_brief_link(self.project), second)

    def test_brief_link_create_view(self):
        response = self.client.post(
            reverse("documents:brief_link_create", args=[self.project.pk]),
        )
        self.assertRedirects(
            response, f"{self.project.get_absolute_url()}?tab=documents",
        )
        self.assertTrue(
            self.link_model.objects.filter(project=self.project, is_active=True).exists(),
        )

    def test_expired_or_missing_link_returns_404(self):
        response = self.client.get(reverse("project_brief_apply", args=["no-such-token"]))
        self.assertEqual(response.status_code, 404)

        link = services.issue_brief_link(self.project)
        link.deactivate()
        self.client.logout()
        response = self.client.get(reverse("project_brief_apply", args=[link.token]))
        self.assertEqual(response.status_code, 404)

    def test_missing_required_field_rejects_submission(self):
        link = services.issue_brief_link(self.project)
        self.client.logout()
        payload = self._payload()
        del payload["goal"]
        response = self.client.post(
            reverse("project_brief_apply", args=[link.token]), payload,
        )
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertIsNone(self.project.client)

    def test_full_submission_creates_client_brief_and_document(self):
        from apps.documents.models import BRIEF, Document, DocumentStatus, ProjectBrief

        link = services.issue_brief_link(self.project, user=self.user)
        self.client.logout()
        response = self.client.post(
            reverse("project_brief_apply", args=[link.token]), self._payload(),
        )
        self.assertEqual(response.status_code, 200)

        self.project.refresh_from_db()
        self.assertIsNotNone(self.project.client)
        self.assertEqual(self.project.client.organization, "ООО Ромашка")
        self.assertEqual(self.project.client.phone, "0700111222")

        brief = ProjectBrief.objects.get(project=self.project)
        self.assertEqual(brief.goal, "Интернет-магазин")
        self.assertIsNotNone(brief.submitted_at)

        document = Document.objects.get(project=self.project, doc_type__code=BRIEF)
        self.assertEqual(document.status, DocumentStatus.DRAFT)

        link.refresh_from_db()
        self.assertEqual(link.submissions, 1)

    def test_resubmission_updates_same_brief_not_duplicate(self):
        from apps.documents.models import BRIEF, Document, ProjectBrief

        link = services.issue_brief_link(self.project)
        self.client.logout()
        self.client.post(
            reverse("project_brief_apply", args=[link.token]), self._payload(),
        )
        self.client.post(
            reverse("project_brief_apply", args=[link.token]),
            self._payload(goal="Обновлённая цель"),
        )
        self.assertEqual(ProjectBrief.objects.filter(project=self.project).count(), 1)
        self.assertEqual(
            Document.objects.filter(project=self.project, doc_type__code=BRIEF).count(), 1,
        )
        brief = ProjectBrief.objects.get(project=self.project)
        self.assertEqual(brief.goal, "Обновлённая цель")

    def test_documents_tab_shows_link_banner_and_submitted_brief(self):
        link = services.issue_brief_link(self.project, user=self.user)
        response = self.client.get(
            f"{self.project.get_absolute_url()}?tab=documents",
        )
        self.assertContains(response, link.token)

        self.client.logout()
        self.client.post(
            reverse("project_brief_apply", args=[link.token]), self._payload(),
        )
        self.client.force_login(self.user)
        response = self.client.get(
            f"{self.project.get_absolute_url()}?tab=documents",
        )
        self.assertContains(response, "Продаём цветы")
