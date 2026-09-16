from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.documents import services
from apps.documents.forms import DocumentForm, DocumentTemplateForm
from apps.documents.models import (
    Document, DocumentStatus, DocumentTemplate, DocumentType,
)
from apps.projects.models import Project, ProjectStatusHistory


@login_required
def document_list(request):
    services.ensure_default_types()
    qs = (
        Document.objects.active()
        .select_related('project', 'doc_type')
    )
    params = request.GET
    if params.get('project'):
        qs = qs.filter(project_id=params['project'])
    if params.get('type'):
        qs = qs.filter(doc_type_id=params['type'])
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    paginator = Paginator(qs, 50)
    page = paginator.get_page(params.get('page'))
    context = {
        'page': page,
        'params': params,
        'projects': Project.objects.active().order_by('name'),
        'doc_types': DocumentType.objects.all(),
        'statuses': DocumentStatus.choices,
    }
    return render(request, 'documents/list.html', context)


@login_required
def document_create(request):
    services.ensure_default_types()
    initial = {}
    if request.GET.get('project'):
        initial['project'] = request.GET['project']
    if request.GET.get('type'):
        initial['doc_type'] = request.GET['type']
    form = DocumentForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        document = form.save()
        messages.success(request, f'Документ «{document.doc_type}» добавлен.')
        return redirect(f'{document.project.get_absolute_url()}?tab=documents')
    return render(
        request, 'documents/form.html',
        {'form': form, 'title': 'Новый документ'},
    )


@login_required
def document_update(request, pk):
    document = get_object_or_404(Document.objects.select_related('project'), pk=pk)
    form = DocumentForm(request.POST or None, request.FILES or None, instance=document)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Документ обновлён.')
        return redirect(f'{document.project.get_absolute_url()}?tab=documents')
    return render(
        request, 'documents/form.html',
        {'form': form, 'title': f'Редактирование: {document.doc_type}'},
    )


@login_required
def document_approve(request, pk):
    """Утвердить документ: бриф принят, ТЗ согласовано с заказчиком."""
    document = get_object_or_404(
        Document.objects.select_related("project", "doc_type"), pk=pk,
    )
    if request.method == "POST":
        document.status = DocumentStatus.SIGNED
        document.is_signed = True
        if not document.signed_date:
            document.signed_date = timezone.localdate()
        document.save(update_fields=[
            "status", "is_signed", "signed_date", "updated_at",
        ])
        ProjectStatusHistory.objects.create(
            project=document.project, field="Документы",
            new_value=f"Утверждён: {document.doc_type}", user=request.user,
        )
        messages.success(request, f"«{document.doc_type}» утверждён.")
    return redirect(f"{document.project.get_absolute_url()}?tab=documents")


@login_required
def template_list(request):
    """Шаблоны документов — не привязаны к проекту, второй раздел
    страницы «Документы» рядом со списком по проектам."""
    services.ensure_default_types()
    templates = DocumentTemplate.objects.select_related('doc_type', 'uploaded_by')
    return render(request, 'documents/template_list.html', {
        'templates': templates,
    })


@login_required
def template_create(request):
    services.ensure_default_types()
    form = DocumentTemplateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        template = form.save(commit=False)
        template.uploaded_by = request.user
        template.save()
        messages.success(request, f'Шаблон «{template}» добавлен.')
        return redirect('documents:templates')
    return render(
        request, 'documents/template_form.html',
        {'form': form, 'title': 'Новый шаблон документа'},
    )


@login_required
def template_update(request, pk):
    template = get_object_or_404(DocumentTemplate, pk=pk)
    form = DocumentTemplateForm(
        request.POST or None, request.FILES or None, instance=template,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Шаблон обновлён.')
        return redirect('documents:templates')
    return render(
        request, 'documents/template_form.html',
        {'form': form, 'title': f'Редактирование шаблона: {template}'},
    )


@login_required
def template_delete(request, pk):
    template = get_object_or_404(DocumentTemplate, pk=pk)
    if request.method == 'POST':
        name = str(template)
        template.delete()
        messages.success(request, f'Шаблон «{name}» удалён.')
    return redirect('documents:templates')
