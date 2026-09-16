from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.training import selectors
from apps.training.forms import TrainingGroupForm
from apps.training.models import GroupStatus, Specialization, TrainingGroup


def _horizon(request) -> int:
    raw = request.GET.get('months', '12')
    return int(raw) if raw in dict(selectors.HORIZONS) else 12


@login_required
def plan(request):
    """План-график академии: кто выпускается по месяцам и сколько придёт."""
    months = _horizon(request)
    rows = selectors.plan(months)
    return render(request, 'training/plan.html', {
        'rows': rows,
        'totals': selectors.plan_totals(rows),
        'academy': selectors.academy_totals(),
        'specs': selectors.by_specialization(months),
        'months': str(months),
        'horizons': selectors.HORIZONS,
    })


@login_required
def group_list(request):
    """Группы академии: всё, из чего складывается план."""
    qs = TrainingGroup.objects.select_related('specialization')
    params = request.GET
    if params.get('specialization'):
        qs = qs.filter(specialization_id=params['specialization'])
    if params.get('status'):
        qs = qs.filter(status=params['status'])
    else:
        qs = qs.filter(status__in=[GroupStatus.RECRUITING, GroupStatus.STUDYING])
    if params.get('branch'):
        qs = qs.filter(branch=params['branch'])
    return render(request, 'training/group_list.html', {
        'groups': qs.order_by('end_date', 'number'),
        'params': params,
        'statuses': GroupStatus.choices,
        'specializations': Specialization.objects.all(),
        'branches': (
            TrainingGroup.objects.exclude(branch='')
            .values_list('branch', flat=True).distinct().order_by('branch')
        ),
    })


@login_required
def group_create(request):
    form = TrainingGroupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        group = form.save()
        messages.success(request, f'Группа {group.number} добавлена.')
        return redirect('training:group_list')
    return render(request, 'training/group_form.html', {
        'form': form, 'title': 'Новая группа академии',
    })


@login_required
def group_update(request, pk):
    group = get_object_or_404(TrainingGroup, pk=pk)
    form = TrainingGroupForm(request.POST or None, instance=group)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Группа {group.number} обновлена.')
        return redirect('training:group_list')
    return render(request, 'training/group_form.html', {
        'form': form, 'title': f'Группа {group.number}', 'group': group,
    })


@login_required
def group_delete(request, pk):
    group = get_object_or_404(TrainingGroup, pk=pk)
    if request.method == 'POST':
        if group.interns.exists():
            messages.error(
                request,
                f'Группу {group.number} нельзя удалить: на неё ссылаются стажёры. '
                'Поставьте статус «Не состоялась» или «Выпущена».',
            )
        else:
            number = group.number
            group.delete()
            messages.success(request, f'Группа {number} удалена.')
    return redirect('training:group_list')
