from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.reports import services
from apps.reports.models import KPISnapshot, WeeklyReport


@login_required
def weekly_list(request):
    return render(request, 'reports/weekly_list.html', {
        'reports': WeeklyReport.objects.all()[:26],
    })


@login_required
def weekly_generate(request):
    if request.method == 'POST':
        report = services.generate_weekly_report()
        messages.success(request, f'Отчёт «{report}» сформирован.')
        return redirect('reports:weekly_detail', pk=report.pk)
    return redirect('reports:weekly_list')


@login_required
def weekly_detail(request, pk):
    report = get_object_or_404(WeeklyReport, pk=pk)
    if request.method == 'POST':
        report.comment = request.POST.get('comment', '')
        report.save(update_fields=['comment', 'updated_at'])
        messages.success(request, 'Комментарий сохранён.')
        return redirect('reports:weekly_detail', pk=report.pk)
    previous = WeeklyReport.objects.filter(
        week_start__lt=report.week_start,
    ).first()
    rows = []
    for key, label in services.WEEKLY_LABELS.items():
        value = report.data.get(key)
        prev_value = previous.data.get(key) if previous else None
        delta = None
        if value is not None and prev_value is not None:
            delta = value - prev_value
        rows.append({'label': label, 'value': value, 'delta': delta})
    return render(request, 'reports/weekly_detail.html', {
        'report': report, 'rows': rows, 'previous': previous,
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
