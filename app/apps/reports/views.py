import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.reports import services, weekly_form
from apps.reports.models import KPISnapshot, WeeklyReport


@login_required
def weekly_list(request):
    """Недельные отчёты: список и кнопки за эту и прошлую неделю."""
    today = timezone.localdate()
    this_week, _ = weekly_form.week_bounds(today)
    last_week = this_week - datetime.timedelta(days=7)
    return render(request, 'reports/weekly_list.html', {
        'reports': WeeklyReport.objects.all()[:26],
        'this_week': this_week,
        'this_week_end': this_week + datetime.timedelta(days=6),
        'last_week': last_week,
        'last_week_end': last_week + datetime.timedelta(days=6),
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
