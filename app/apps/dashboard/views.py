from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.dashboard import selectors


@login_required
def dashboard(request):
    context = {
        'kpi_cards': selectors.kpi_cards(),
        'attention_items': selectors.attention_items(),
        'today_items': selectors.today_items(),
    }
    return render(request, 'dashboard/index.html', context)
