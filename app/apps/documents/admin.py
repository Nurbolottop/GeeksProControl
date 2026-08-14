from django.contrib import admin

from apps.documents.models import Document, DocumentType


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'required_for_delivery')
    list_editable = ('required_for_delivery',)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'project', 'doc_type', 'number', 'status',
        'is_signed', 'signed_date', 'is_archived',
    )
    list_filter = ('doc_type', 'status', 'is_signed', 'is_archived')
    search_fields = ('number', 'project__name')
