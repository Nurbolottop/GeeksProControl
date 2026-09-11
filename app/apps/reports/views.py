import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.reports import services, weekly_form
from apps.reports.models import KPISnapshot, WeeklyReport, WrittenNote


@login_required
def weekly_list(request):
    """Недельные отчёты: список и кнопки за эту и прошлую неделю."""
    today = timezone.localdate()
    this_week, _ = weekly_form.week_bounds(today)
    # Отчёт всегда смотрит назад: основная кнопка — прошедшая неделя
    last_week = this_week - datetime.timedelta(days=7)
    before_last = last_week - datetime.timedelta(days=7)
    return render(request, 'reports/weekly_list.html', {
        'reports': WeeklyReport.objects.all()[:26],
        'last_week': last_week,
        'last_week_end': last_week + datetime.timedelta(days=6),
        'before_last': before_last,
        'before_last_end': before_last + datetime.timedelta(days=6),
    })


@login_required
def weekly_generate(request):
    """Считает отчёт за выбранную неделю."""
    if request.method != 'POST':
        return redirect('reports:weekly_list')
    today = timezone.localdate()
    try:
        day = datetime.date.fromisoformat(request.POST.get('week', ''))
    except ValueError:
        day = today
    week_start, week_end = weekly_form.week_bounds(day)

    report, _ = WeeklyReport.objects.update_or_create(
        week_start=week_start,
        defaults={'data': weekly_form.build(week_start)},
    )
    messages.success(
        request,
        f'Отчёт за неделю {week_start:%d.%m} — {week_end:%d.%m.%Y} готов.',
    )
    return redirect('reports:weekly_detail', pk=report.pk)


@login_required
def weekly_detail(request, pk):
    report = get_object_or_404(WeeklyReport, pk=pk)
    return render(request, 'reports/weekly_detail.html', {
        'report': report,
        'week_end': report.week_start + datetime.timedelta(days=6),
        'sections': weekly_form.as_sections(report.data),
    })


@login_required
def kpi_view(request):
    kpi = services.calculate_kpi()
    cards = []
    for key, (label, suffix) in services.KPI_LABELS.items():
        value = kpi.get(key)
        cards.append({
            'label': label,
            'value': f'{value}{suffix}' if value is not None else '—',
        })
    snapshots = KPISnapshot.objects.filter(
        period_type=KPISnapshot.Period.WEEK,
    )[:12]
    if request.method == 'POST':
        services.snapshot_kpi()
        messages.success(request, 'KPI snapshot сохранён.')
        return redirect('reports:kpi')
    return render(request, 'reports/kpi.html', {
        'cards': cards, 'snapshots': snapshots,
        'kpi_labels': services.KPI_LABELS,
    })


@login_required
def weekly_delete(request, pk):
    """Удаление недельного отчёта вместе с написанным текстом."""
    report = get_object_or_404(WeeklyReport, pk=pk)
    if request.method == "POST":
        week = report.week_start
        report.delete()
        messages.success(request, f"Отчёт за неделю {week:%d.%m.%Y} удалён.")
    return redirect("reports:weekly_list")


@login_required
def written_list(request):
    """Записи за неделю: достижения, проблемы и вопросы."""
    today = timezone.localdate()
    # По умолчанию — прошедшая неделя: отчёт пишется по факту, а не наперёд
    default_day = today - datetime.timedelta(days=7)
    try:
        day = datetime.date.fromisoformat(request.GET.get('week', ''))
    except ValueError:
        day = default_day
    week_start, week_end = weekly_form.week_bounds(day)

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        kind = request.POST.get('kind', '')
        if kind not in WrittenNote.Kind.values:
            kind = WrittenNote.Kind.ACHIEVEMENT
        if not text:
            messages.error(request, 'Пустая запись — напишите текст.')
        else:
            note = WrittenNote.objects.create(
                kind=kind, text=text, week_start=week_start,
                author=request.user,
            )
            messages.success(request, f'{note.get_kind_display()} добавлено.')
        return redirect(
            f"{reverse('reports:written_list')}?week={week_start:%Y-%m-%d}",
        )

    notes = list(
        WrittenNote.objects.filter(week_start=week_start)
        .select_related('author'),
    )
    titles = {
        WrittenNote.Kind.ACHIEVEMENT: 'Достижения',
        WrittenNote.Kind.PROBLEM: 'Проблемы',
        WrittenNote.Kind.QUESTION: 'Вопросы',
    }
    sections = [
        {
            'key': kind,
            'label': titles.get(kind, label),
            'notes': [note for note in notes if note.kind == kind],
        }
        for kind, label in WrittenNote.Kind.choices
    ]
    return render(request, 'reports/written_list.html', {
        'sections': sections,
        'kinds': WrittenNote.Kind.choices,
        'total': len(notes),
        'week_start': week_start,
        'week_end': week_end,
        'prev_week': week_start - datetime.timedelta(days=7),
        'next_week': week_start + datetime.timedelta(days=7),
        'is_default_week': week_start == weekly_form.week_bounds(default_day)[0],
        'is_future_week': week_start > weekly_form.week_bounds(today)[0],
    })


@login_required
def written_update(request, pk):
    """Правка записи."""
    note = get_object_or_404(WrittenNote, pk=pk)
    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            note.text = text
            note.save(update_fields=['text', 'updated_at'])
            messages.success(request, 'Запись обновлена.')
        else:
            messages.error(request, 'Пустая запись — не сохранено.')
    return redirect(
        f"{reverse('reports:written_list')}?week={note.week_start:%Y-%m-%d}",
    )


@login_required
def written_delete(request, pk):
    """Удаление записи."""
    note = get_object_or_404(WrittenNote, pk=pk)
    if request.method == 'POST':
        label = note.get_kind_display()
        week = note.week_start
        note.delete()
        messages.success(request, f'{label} удалено.')
        return redirect(
            f"{reverse('reports:written_list')}?week={week:%Y-%m-%d}",
        )
    return redirect('reports:written_list')
