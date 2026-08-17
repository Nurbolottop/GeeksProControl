from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.documents import services
from apps.documents.forms import DocumentForm
from apps.documents.models import Document, DocumentStatus, DocumentType
from apps.projects.models import Project


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
