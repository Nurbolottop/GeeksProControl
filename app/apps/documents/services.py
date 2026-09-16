"""Контроль комплекта документов проекта (ТЗ §17.1)."""
from django.db import models

from apps.documents.models import (
    BRIEF,
    DEFAULT_TYPES,
    Document,
    DocumentStatus,
    DocumentType,
    ProjectBrief,
    ProjectBriefLink,
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


# --- Бриф по ссылке ---------------------------------------------------
# ПМ выпускает ссылку на конкретный проект и отправляет её заказчику сам
# (WhatsApp/Telegram/email — вручную). Заполнение обновляет одну и ту же
# карточку ProjectBrief проекта, а не плодит новые записи при повторной
# отправке.

def issue_brief_link(project: Project, user=None, ttl_days: int | None = 30) -> ProjectBriefLink:
    """Новая ссылка на бриф проекта, гася прежние активные ссылки этого
    же проекта — чтобы старая, отправленная по ошибке, не гуляла дальше."""
    from datetime import timedelta

    from django.utils import timezone

    ProjectBriefLink.objects.filter(project=project, is_active=True).update(
        is_active=False,
    )
    return ProjectBriefLink.objects.create(
        project=project,
        created_by=user if user and user.is_authenticated else None,
        expires_at=timezone.now() + timedelta(days=ttl_days) if ttl_days else None,
    )


def active_brief_link(project: Project) -> ProjectBriefLink | None:
    """Действующая ссылка на бриф проекта или None."""
    from django.utils import timezone

    link = (
        ProjectBriefLink.objects.filter(project=project, is_active=True)
        .order_by('-created_at').first()
    )
    if link is not None and link.is_expired:
        link.is_active = False
        link.save(update_fields=['is_active', 'updated_at'])
        return None
    return link


def accept_brief_submission(link: ProjectBriefLink, form) -> ProjectBrief:
    """Заказчик отправил бриф по ссылке.

    Контакты уходят в карточку клиента проекта (создаётся, если её ещё
    не было), остальные ответы — в ProjectBrief. Плюс автоматически
    заводится/обновляется Document(doc_type=brief, status=DRAFT) —
    ПМ увидит его в чек-листе «Документы» и утвердит после проверки,
    как любой другой загруженный документ.
    """
    from django.utils import timezone

    from apps.clients.models import Client

    ensure_default_types()
    now = timezone.now()
    project = link.project
    data = form.cleaned_data

    client = project.client or Client()
    client.organization = data['organization']
    client.contact_name = data['contact_name']
    client.phone = data['phone']
    client.email = data['email']
    client.save()
    if project.client_id != client.pk:
        project.client = client
        project.save(update_fields=['client', 'updated_at'])

    brief = form.save(commit=False)
    brief.project = project
    brief.submitted_at = now
    brief.save()

    doc_type = DocumentType.objects.get(code=BRIEF)
    document, _ = Document.objects.get_or_create(
        project=project, doc_type=doc_type,
        defaults={'status': DocumentStatus.DRAFT, 'document_date': now.date()},
    )
    if document.status in (DocumentStatus.CANCELLED, DocumentStatus.EXPIRED):
        document.status = DocumentStatus.DRAFT
        document.save(update_fields=['status', 'updated_at'])

    ProjectBriefLink.objects.filter(pk=link.pk).update(
        submissions=models.F('submissions') + 1, used_at=now,
    )
    return brief
