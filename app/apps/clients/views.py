from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.clients.forms import ClientForm
from apps.clients.models import Client


@login_required
def client_list(request):
    qs = (
        Client.objects.active()
        .annotate(project_count=Count('projects'))
        .order_by('organization')
    )
    search = request.GET.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(organization__icontains=search)
            | Q(contact_name__icontains=search)
            | Q(phone__icontains=search),
        )
    city = request.GET.get('city')
    if city:
        qs = qs.filter(city=city)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    cities = (
        Client.objects.active().exclude(city='')
        .values_list('city', flat=True).distinct().order_by('city')
    )
    return render(
        request, 'clients/list.html',
        {'page': page, 'cities': cities, 'params': request.GET},
    )


@login_required
def client_detail(request, pk):
    client = get_object_or_404(Client, pk=pk)
    projects = client.projects.select_related('project_type')
    return render(
        request, 'clients/detail.html',
        {'client': client, 'projects': projects},
    )


@login_required
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        client = form.save()
        messages.success(request, f'Клиент «{client.organization}» добавлен.')
        return redirect('clients:detail', pk=client.pk)
    return render(
        request, 'clients/form.html',
        {'form': form, 'title': 'Новый клиент'},
    )


@login_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Клиент обновлён.')
        return redirect('clients:detail', pk=client.pk)
    return render(
        request, 'clients/form.html',
        {'form': form, 'title': f'Редактирование: {client.organization}'},
    )
