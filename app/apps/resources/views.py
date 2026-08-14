from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render

from apps.resources import services
from apps.resources.models import PlannedProject, PlannedProjectNeed


class PlannedProjectForm(forms.ModelForm):
    class Meta:
        model = PlannedProject
        fields = [
            'name', 'status', 'probability', 'expected_start',
            'project_type', 'duration_months', 'comment',
        ]
        widgets = {
            'expected_start': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }


NeedFormSet = inlineformset_factory(
    PlannedProject, PlannedProjectNeed,
    fields=['specialization', 'count'], extra=2, can_delete=True,
)


@login_required
def forecast(request):
    """Прогноз потребности (ТЗ §14)."""
    return render(request, 'resources/forecast.html', {
        'rows': services.resource_balance(),
        'planned': (
            PlannedProject.objects
            .exclude(status__in=[
                PlannedProject.Status.LAUNCHED, PlannedProject.Status.REJECTED,
            ])
            .prefetch_related('needs__specialization')
        ),
    })


@login_required
def graduations(request):
    """Будущие выпуски учебных групп (ТЗ §13)."""
    return render(request, 'resources/graduations.html', {
        'groups': services.upcoming_graduations(),
    })


@login_required
def planned_create(request):
    form = PlannedProjectForm(request.POST or None)
    formset = NeedFormSet(request.POST or None)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        planned = form.save()
        formset.instance = planned
        formset.save()
        messages.success(request, f'Планируемый проект «{planned.name}» создан.')
        return redirect('resources:forecast')
    return render(
        request, 'resources/planned_form.html',
        {'form': form, 'formset': formset, 'title': 'Планируемый проект'},
    )


@login_required
def planned_update(request, pk):
    planned = get_object_or_404(PlannedProject, pk=pk)
    form = PlannedProjectForm(request.POST or None, instance=planned)
    formset = NeedFormSet(request.POST or None, instance=planned)
    if request.method == 'POST' and form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        messages.success(request, 'Планируемый проект обновлён.')
        return redirect('resources:forecast')
    return render(
        request, 'resources/planned_form.html',
        {'form': form, 'formset': formset, 'title': f'Редактирование: {planned.name}'},
    )
