import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.dailycheck import overview
from apps.dailycheck.models import CheckItem, CheckMark, ensure_default_items


# Порядок блоков на странице — как проходят проверку утром
BLOCK_ORDER = [
    CheckItem.Block.PROJECTS,
    CheckItem.Block.MEETINGS,
    CheckItem.Block.PEOPLE,
    CheckItem.Block.OFFICE,
]


def _day(request) -> datetime.date:
    raw = request.GET.get('date', '')
    if not raw:
        return timezone.localdate()
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        raise Http404('Некорректная дата')


def _rows(day: datetime.date) -> list[dict]:
    """Пункты проверки за день, сгруппированные по блокам."""
    items = list(CheckItem.objects.filter(is_active=True))
    marks = {
        mark.item_id: mark
        for mark in CheckMark.objects.filter(date=day).select_related('checked_by')
    }
    blocks: dict[str, dict] = {}
    for item in items:
        mark = marks.get(item.pk)
        block = blocks.setdefault(item.block, {
            'key': item.block,
            'label': item.get_block_display(),
            'items': [],
            'done': 0,
        })
        block['items'].append({
            'item': item,
            'date': day,
            'mark': mark,
            'is_done': bool(mark and mark.is_done),
            'note': mark.note if mark else '',
        })
        if mark and mark.is_done:
            block['done'] += 1
    return [blocks[key] for key in BLOCK_ORDER if key in blocks]


@login_required
def index(request):
    """Ежедневная проверка: цифры на сегодня и чек-лист с отметками."""
    ensure_default_items()
    day = _day(request)
    today = timezone.localdate()
    blocks = _rows(day)

    total = sum(len(block['items']) for block in blocks)
    done = sum(block['done'] for block in blocks)

    return render(request, 'dailycheck/index.html', {
        'day': day,
        'today': today,
        'is_today': day == today,
        'prev_day': day - datetime.timedelta(days=1),
        'next_day': day + datetime.timedelta(days=1),
        'blocks': blocks,
        'total': total,
        'done': done,
        'percent': round(done / total * 100) if total else 0,
        'all_done': total and done >= total,
        'cards': overview.cards(day),
        'week': overview.last_days(today=today),
    })


@login_required
def toggle(request, pk):
    """AJAX: отметить / снять отметку по пункту за день."""
    if request.method != 'POST':
        raise Http404
    item = get_object_or_404(CheckItem, pk=pk)
    day = _day_from_post(request)

    mark = CheckMark.objects.filter(date=day, item=item).first()
    if mark and mark.is_done:
        mark.delete()
        mark = None
    else:
        mark = CheckMark.objects.create(
            date=day, item=item, is_done=True, checked_by=request.user,
        )
    return render(request, 'dailycheck/partials/row.html', {
        'row': {
            'item': item, 'date': day, 'mark': mark,
            'is_done': bool(mark), 'note': mark.note if mark else '',
        },
    })


@login_required
def note(request, pk):
    """AJAX: заметка по пункту — что увидел при проверке."""
    if request.method != 'POST':
        raise Http404
    item = get_object_or_404(CheckItem, pk=pk)
    day = _day_from_post(request)
    text = request.POST.get('note', '').strip()[:255]

    mark = CheckMark.objects.filter(date=day, item=item).first()
    if mark:
        mark.note = text
        mark.checked_by = request.user
        mark.save(update_fields=['note', 'checked_by', 'updated_at'])
    elif text:
        mark = CheckMark.objects.create(
            date=day, item=item, is_done=False, note=text,
            checked_by=request.user,
        )
    return render(request, 'dailycheck/partials/row.html', {
        'row': {
            'item': item, 'date': day, 'mark': mark,
            'is_done': bool(mark and mark.is_done),
            'note': mark.note if mark else '',
        },
    })


def _day_from_post(request) -> datetime.date:
    try:
        return datetime.date.fromisoformat(request.POST.get('date', ''))
    except ValueError:
        return timezone.localdate()


@login_required
def item_create(request):
    """Добавить свой пункт в ежедневную проверку."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()[:200]
        block = request.POST.get('block', CheckItem.Block.OFFICE)
        if title:
            if block not in CheckItem.Block.values:
                block = CheckItem.Block.OFFICE
            CheckItem.objects.create(
                title=title, block=block,
                hint=request.POST.get('hint', '').strip()[:255],
                order=(CheckItem.objects.filter(block=block).count() + 1) * 10,
            )
            messages.success(request, f'Пункт «{title}» добавлен в проверку.')
        else:
            messages.error(request, 'Напишите, что проверять.')
    return redirect('dailycheck:index')


@login_required
def item_delete(request, pk):
    """Убрать пункт из ежедневной проверки (история отметок сохраняется)."""
    item = get_object_or_404(CheckItem, pk=pk)
    if request.method == 'POST':
        item.is_active = False
        item.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Пункт «{item.title}» убран.')
    return redirect('dailycheck:index')
