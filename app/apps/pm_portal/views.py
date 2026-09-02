from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.pm_portal import services
from apps.projects.models import ProjectReport
from apps.projects.services import calculate_deadline_status


@login_required
def dashboard(request):
    """Список проектов, где текущий пользователь — активный ПМ."""
    return render(request, 'pm_portal/dashboard.html', {
        'projects': services.pm_projects(request.user),
    })


@login_required
def project_detail(request, pk):
    """Обзор проекта — только чтение: статус/этап/дедлайн менять здесь нельзя."""
    project = services.pm_project_or_404(request.user, pk)
    project.deadline_status = calculate_deadline_status(project)
    tab = request.GET.get('tab', 'overview')
    context = {'project': project, 'tab': tab}
    if tab == 'report':
        context['reports'] = project.reports.select_related('author')
    return render(request, 'pm_portal/project_detail.html', context)


@login_required
def report_create(request, pk):
    project = services.pm_project_or_404(request.user, pk)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if not text:
            messages.error(request, 'Отчёт пустой — напишите текст.')
        else:
            report = ProjectReport.objects.create(
                project=project, text=text, author=request.user,
            )
            messages.success(request, f'Отчёт от {report.date:%d.%m.%Y} сохранён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")


@login_required
def report_update(request, pk, report_pk):
    project = services.pm_project_or_404(request.user, pk)
    report = get_object_or_404(ProjectReport, pk=report_pk, project=project)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            report.text = text
            report.save(update_fields=['text', 'updated_at'])
            messages.success(request, 'Отчёт обновлён.')
        else:
            messages.error(request, 'Отчёт пустой — текст не сохранён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")


@login_required
def report_delete(request, pk, report_pk):
    project = services.pm_project_or_404(request.user, pk)
    report = get_object_or_404(ProjectReport, pk=report_pk, project=project)
    if request.method == 'POST':
        date = report.date
        report.delete()
        messages.success(request, f'Отчёт от {date:%d.%m.%Y} удалён.')
    return redirect(f"{reverse('pm_portal:project_detail', args=[project.pk])}?tab=report")
