from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.pm_portal import services
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
    return render(request, 'pm_portal/project_detail.html', {
        'project': project,
    })
