from django.test import TestCase

from apps.documents import services
from apps.documents.models import (
    BRIEF,
    CONTRACT,
    FINAL_ACT,
    Document,
    DocumentStatus,
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
        # бриф, договор, ТЗ, финальный акт
        self.assertEqual(progress['total'], 4)

        self._add(CONTRACT)
        progress = services.document_progress(self.project)
        self.assertEqual(progress['done'], 1)
        missing_codes = {t.code for t in progress['missing']}
        self.assertEqual(missing_codes, {BRIEF, REQUIREMENTS, FINAL_ACT})

    def test_cancelled_document_not_counted(self):
        self._add(CONTRACT, status=DocumentStatus.CANCELLED)
        progress = services.document_progress(self.project)
        self.assertEqual(progress['done'], 0)

    def test_signed_check(self):
        self._add(FINAL_ACT)
        self.assertFalse(services.has_signed_document(self.project, FINAL_ACT))
        self.project.documents.update(is_signed=True)
        self.assertTrue(services.has_signed_document(self.project, FINAL_ACT))
