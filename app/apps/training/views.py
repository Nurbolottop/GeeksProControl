from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.training import importer, selectors
from apps.training.forms import ImportForm, TrainingGroupForm
from apps.training.models import GroupStatus, Specialization, TrainingGroup


def _horizon(request) -> int:
    raw = request.GET.get('months', '12')
    return int(raw) if raw in dict(selectors.HORIZONS) else 12


@login_required
def plan(request):
    """IT-академия по направлениям: когда и сколько студентов выпускается."""
    months = _horizon(request)
    return render(request, 'training/plan.html', {
        'grid': selectors.matrix(months),
        'directions': selectors.directions(),
        'silent': selectors.silent_directions(),
        'academy': selectors.academy_totals(),
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
    if params.get('branch'):
        qs = qs.filter(branch=params['branch'])
    groups = list(qs.order_by('end_date', 'specialization__name', 'number'))
    stage = params.get('status')
    if stage:
        groups = [group for group in groups if group.stage == stage]
    else:
        groups = [group for group in groups if group.is_open]
    return render(request, 'training/group_list.html', {
        'groups': groups,
        'params': params,
        'statuses': GroupStatus.choices,
        'specializations': Specialization.objects.all(),
        'branches': (
            TrainingGroup.objects.exclude(branch='')
            .values_list('branch', flat=True).distinct().order_by('branch')
        ),
    })


@login_required
def group_import(request):
    """Вставить сообщение академии: сначала показываем, что поменяется."""
    form = ImportForm(request.POST or None)
    rows = None
    if request.method == 'POST' and form.is_valid():
        rows = importer.parse(form.cleaned_data['text'])
        if request.POST.get('confirm') and rows:
            result = importer.apply(rows)
            parts = [
                f'добавлено групп: {result["created"]}',
                f'обновлено: {result["updated"]}',
            ]
            if result['same']:
                parts.append(f'без изменений: {result["same"]}')
            if result['skipped']:
                parts.append(f'пропущено с ошибками: {result["skipped"]}')
            messages.success(request, 'Группы академии загружены — ' + ', '.join(parts) + '.')
            return redirect('training:plan')
    return render(request, 'training/import.html', {
        'form': form,
        'rows': rows,
        'has_changes': bool(rows) and any(
            row.action in ('create', 'update') for row in rows
        ),
    })


@login_required
def group_create(request):
    form = TrainingGroupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        group = form.save()
        messages.success(request, f'Группа {group} добавлена.')
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
        messages.success(request, f'Группа {group} обновлена.')
        return redirect('training:group_list')
    return render(request, 'training/group_form.html', {
        'form': form, 'title': f'Группа {group}', 'group': group,
    })


@login_required
def group_delete(request, pk):
    group = get_object_or_404(TrainingGroup, pk=pk)
    if request.method == 'POST':
        if group.interns.exists():
            messages.error(
                request,
                f'Группу {group} нельзя удалить: на неё ссылаются стажёры. '
                'Отметьте «Группа не состоялась».',
            )
        else:
            name = str(group)
            group.delete()
            messages.success(request, f'Группа {name} удалена.')
    return redirect('training:group_list')
