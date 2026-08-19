"""Контроль комплекта документов проекта (ТЗ §17.1)."""
from apps.documents.models import (
    DEFAULT_TYPES,
    Document,
    DocumentStatus,
    DocumentType,
)
from apps.projects.models import Project


def ensure_default_types() -> None:
    """Досоздаёт недостающие типы документов.

    Проверяется каждый тип по отдельности, поэтому новые типы
    (например, бриф) появляются и на уже работающей базе.
    """
    existing = set(DocumentType.objects.values_list('code', flat=True))
    missing = [
        DocumentType(code=code, name=name, required_for_delivery=required)
        for code, name, required in DEFAULT_TYPES
        if code not in existing
    ]
    if missing:
        DocumentType.objects.bulk_create(missing)


def document_progress(project: Project) -> dict:
    """Прогресс комплекта обязательных документов: «Документы: 2/3».

    Обязательный документ считается закрытым, если он загружен
    и не отменён/не истёк.
    """
    ensure_default_types()
    required_types = list(DocumentType.objects.filter(required_for_delivery=True))
    present_type_ids = set(
        project.documents.active()
        .exclude(status__in=[DocumentStatus.CANCELLED, DocumentStatus.EXPIRED])
        .values_list('doc_type_id', flat=True),
    )
    missing = [t for t in required_types if t.pk not in present_type_ids]
    return {
        'total': len(required_types),
        'done': len(required_types) - len(missing),
        'missing': missing,
    }


def has_signed_document(project: Project, type_code: str) -> bool:
    return project.documents.active().filter(
        doc_type__code=type_code, is_signed=True,
    ).exists()


def has_document(project: Project, type_code: str) -> bool:
    return (
        project.documents.active()
        .exclude(status__in=[DocumentStatus.CANCELLED, DocumentStatus.EXPIRED])
        .filter(doc_type__code=type_code)
        .exists()
    )
