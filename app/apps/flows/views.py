from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.flows.models import Flow
from apps.interns.models import Intern, InternStatus, WORKING_STATUSES
from apps.projects import selectors as project_selectors
from apps.projects.models import Project, ProjectStatus
from apps.teams.models import TeamMember


class FlowForm(forms.ModelForm):
    class Meta:
        model = Flow
        fields = ['number', 'status', 'start_date', 'end_date', 'comment']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }


@login_required
def flow_list(request):
    flows = Flow.objects.annotate(
        projects_count=Count('projects', distinct=True),
        interns_count=Count('interns', distinct=True),
    ).order_by('-number')
    rows = []
    for flow in flows:
        active = flow.projects.filter(status=ProjectStatus.ACTIVE).count()
        completed = flow.projects.filter(status=ProjectStatus.COMPLETED).count()
        rows.append({
            'flow': flow,
            'projects': flow.projects_count,
            'interns': flow.interns_count,
            'active': active,
            'completed': completed,
        })
    return render(request, 'flows/list.html', {'rows': rows})


@login_required
def flow_detail(request, pk):
    flow = get_object_or_404(Flow, pk=pk)
    tab = request.GET.get('tab', 'projects')
    context = {'flow': flow, 'tab': tab}

    if tab == 'roster':
        interns = (
            flow.interns.filter(is_archived=False)
            .select_related('specialization', 'training_group')
            .order_by('specialization__name', 'full_name')
        )
        busy = set(
            TeamMember.objects.filter(
                status=TeamMember.Status.ACTIVE, intern__isnull=False,
            ).values_list('intern_id', flat=True),
        )
        for intern in interns:
            intern.is_busy = intern.pk in busy
        context['interns'] = interns
    elif tab == 'stats':
        context['by_spec'] = (
            flow.interns.filter(is_archived=False)
            .values('specialization__name')
            .annotate(total=Count('id'))
            .order_by('-total')
        )
        context['stats'] = {
            'projects': flow.projects.count(),
            'active': flow.projects.filter(status=ProjectStatus.ACTIVE).count(),
            'completed': flow.projects.filter(status=ProjectStatus.COMPLETED).count(),
            'stopped': flow.projects.filter(
                status__in=[ProjectStatus.CANCELLED, ProjectStatus.REFUSED],
            ).count(),
            'interns': flow.interns.filter(is_archived=False).count(),
            'working': flow.interns.filter(
                is_archived=False, status__in=WORKING_STATUSES,
            ).count(),
            'dropped': flow.interns.filter(
                is_archived=False, status=InternStatus.DROPPED,
            ).count(),
        }
    else:
        projects = list(
            flow.projects.select_related('client', 'project_type')
            .order_by('number_in_flow', 'pk')
        )
        project_selectors.annotate_deadline_statuses(projects)
        context['projects'] = projects
    return render(request, 'flows/detail.html', context)


@login_required
def flow_create(request):
    form = FlowForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        flow = form.save()
        messages.success(request, f'{flow} создан.')
        return redirect(flow.get_absolute_url())
    return render(
        request, 'flows/form.html', {'form': form, 'title': 'Новый поток'},
    )


@login_required
def flow_update(request, pk):
    flow = get_object_or_404(Flow, pk=pk)
    form = FlowForm(request.POST or None, instance=flow)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Поток обновлён.')
        return redirect(flow.get_absolute_url())
    return render(
        request, 'flows/form.html',
        {'form': form, 'flow': flow, 'title': f'Редактирование: {flow}'},
    )
