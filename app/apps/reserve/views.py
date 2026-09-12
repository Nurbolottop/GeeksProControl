"""Резерв кадров: список, карточка кандидата, оценка, рекомендации,
приглашения на анкету и сама публичная анкета.

Внутренние страницы закрыты логином (и ролью — на изменение), публичная
анкета доступна только по токену приглашения и не даёт кандидату
ничего, кроме собственной формы.
"""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.interns.models import Intern
from apps.reserve import selectors, services
from apps.reserve.forms import (
    InviteForm, ReserveApplyForm, ReserveCandidateForm, ReserveEvaluationForm,
    ReserveRecommendationForm, StatusChangeForm,
)
from apps.reserve.models import (
    CandidateLevel, CandidateStatus, Employment, RecommendationStatus,
    ReserveCandidate, ReserveInvite, ReserveRecommendation, WorkFormat,
)
from apps.reserve.permissions import can_edit_reserve, reserve_editor_required
from apps.training.models import Specialization


@login_required
def overview(request):
    """Главная резерва: сводка по направлениям, дальше — в список."""
    rows = selectors.summary_by_specialization()
    return render(request, 'reserve/overview.html', {
        'rows': rows,
        'totals': selectors.summary_totals(rows),
        'can_edit': can_edit_reserve(request.user),
        'statuses': {
            'new': [str(s) for s in selectors.NEW_STATUSES],
            'available': [str(s) for s in selectors.AVAILABLE_STATUSES],
            'in_progress': [str(s) for s in selectors.IN_PROGRESS_STATUSES],
        },
    })


@login_required
def candidate_list(request):
    qs, sort = selectors.candidates(request.GET)
    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get('page'))
    open_invites = [
        invite for invite in
        ReserveInvite.objects.filter(is_active=True, candidate__isnull=True)[:20]
        if invite.is_open
    ]
    context = {
        'page': page,
        'params': request.GET,
        'sort': sort,
        'sort_options': selectors.SORT_OPTIONS,
        'rating_options': selectors.RATING_OPTIONS,
        'readiness_options': selectors.READINESS_OPTIONS,
        'specializations': Specialization.objects.all(),
        'levels': CandidateLevel.choices,
        'statuses': CandidateStatus.choices,
        'work_formats': WorkFormat.choices,
        'employments': Employment.choices,
        'cities': selectors.cities(),
        'extra_filters': selectors.extra_filters_used(request.GET),
        'has_filters': selectors.any_filter_used(request.GET),
        'open_invites': open_invites,
        'invite_form': InviteForm(),
        'can_edit': can_edit_reserve(request.user),
        'free_interns': (
            Intern.objects.active().filter(reserve_card__isnull=True)
            .order_by('full_name')
        ),
    }
    return render(request, 'reserve/list.html', context)


@login_required
def candidate_detail(request, pk):
    candidate = get_object_or_404(
        ReserveCandidate.objects.select_related(
            'specialization', 'training_group', 'intern', 'created_by', 'updated_by',
        ),
        pk=pk,
    )
    tab = request.GET.get('tab', 'general')
    if tab not in {
        'general', 'professional', 'skills', 'experience', 'projects',
        'evaluation', 'recommendations', 'history',
    }:
        tab = 'general'
    context = {
        'candidate': candidate,
        'tab': tab,
        'memberships': candidate.project_memberships,
        'recommendations': candidate.recommendations.select_related(
            'company', 'created_by',
        ),
        'events': candidate.events.select_related('user')[:100],
        'status_form': StatusChangeForm(
            initial={'status': candidate.status}, current=candidate.status,
        ),
        'edit_links': [
            link for link in candidate.edit_links.filter(is_active=True)
            if link.is_open
        ],
        'invite_form': InviteForm(),
        'rec_statuses': RecommendationStatus.choices,
        'can_edit': can_edit_reserve(request.user),
    }
    return render(request, 'reserve/detail.html', context)


@reserve_editor_required
def candidate_create(request):
    form = ReserveCandidateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        candidate = services.create_candidate(form.save(commit=False), request.user)
        form.save_m2m()
        messages.success(request, f'{candidate.full_name} добавлен(а) в резерв.')
        return redirect(candidate.get_absolute_url())
    return render(request, 'reserve/form.html', {
        'form': form, 'title': 'Новый кандидат в резерв',
    })


@reserve_editor_required
def candidate_from_intern(request):
    """Быстро завести кандидата из карточки стажёра — без перепечатывания."""
    if request.method == 'POST':
        intern = get_object_or_404(Intern, pk=request.POST.get('intern'))
        candidate = services.candidate_from_intern(intern, request.user)
        messages.success(
            request, f'{candidate.full_name} добавлен(а) в резерв из базы стажёров.',
        )
        return redirect(candidate.get_absolute_url())
    return redirect('reserve:list')


@reserve_editor_required
def candidate_update(request, pk):
    candidate = get_object_or_404(ReserveCandidate, pk=pk)
    form = ReserveCandidateForm(
        request.POST or None, request.FILES or None, instance=candidate,
    )
    if request.method == 'POST' and form.is_valid():
        changed = ', '.join(form.changed_data)
        services.update_candidate(form.save(commit=False), request.user, detail=changed)
        messages.success(request, 'Карточка кандидата обновлена.')
        return redirect(candidate.get_absolute_url())
    return render(request, 'reserve/form.html', {
        'form': form, 'title': f'Резерв: {candidate.full_name}',
        'candidate': candidate,
    })


@reserve_editor_required
def candidate_evaluate(request, pk):
    candidate = get_object_or_404(ReserveCandidate, pk=pk)
    form = ReserveEvaluationForm(request.POST or None, instance=candidate)
    if request.method == 'POST' and form.is_valid():
        services.save_evaluation(form.save(commit=False), request.user)
        messages.success(
            request, f'Оценка сохранена, рейтинг: {candidate.rating or "—"} / 10.',
        )
        return redirect(candidate.get_absolute_url())
    return render(request, 'reserve/evaluate_form.html', {
        'form': form, 'candidate': candidate,
        'criteria': ReserveCandidate.EVALUATION_CRITERIA,
    })


@reserve_editor_required
def candidate_status(request, pk):
    candidate = get_object_or_404(ReserveCandidate, pk=pk)
    # current — чтобы отправка текущего статуса воронки не считалась ошибкой
    form = StatusChangeForm(request.POST or None, current=candidate.status)
    if request.method == 'POST':
        if form.is_valid():
            services.change_status(
                candidate, form.cleaned_data['status'],
                comment=form.cleaned_data['comment'], user=request.user,
            )
            messages.success(request, f'Статус: {candidate.get_status_display()}.')
        else:
            messages.error(request, 'Статус не изменён: выберите его из списка.')
    return redirect(candidate.get_absolute_url())


@reserve_editor_required
def invite_create(request, pk=None):
    """Ссылка на анкету: общая или на редактирование карточки кандидата."""
    candidate = get_object_or_404(ReserveCandidate, pk=pk) if pk else None
    form = InviteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        invite = services.issue_invite(
            candidate, user=request.user, ttl_days=form.ttl(),
            recipient=form.cleaned_data['recipient'],
        )
        kind = 'на редактирование анкеты' if candidate else 'на анкету'
        messages.success(
            request,
            f'Ссылка {kind} создана: '
            f'{request.build_absolute_uri(invite.get_absolute_url())}',
        )
    if candidate is not None:
        return redirect(candidate.get_absolute_url())
    return redirect('reserve:list')


@reserve_editor_required
def invite_disable(request, pk):
    invite = get_object_or_404(ReserveInvite, pk=pk)
    if request.method == 'POST':
        invite.deactivate()
        messages.success(request, 'Ссылка на анкету отключена.')
    if invite.candidate_id:
        return redirect(invite.candidate.get_absolute_url())
    return redirect('reserve:list')


@reserve_editor_required
def recommendation_create(request, pk):
    candidate = get_object_or_404(ReserveCandidate, pk=pk)
    form = ReserveRecommendationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        recommendation = form.save(commit=False)
        recommendation.candidate = candidate
        services.add_recommendation(recommendation, request.user)
        messages.success(
            request, f'Рекомендация в «{recommendation.company_title}» сохранена.',
        )
        return redirect(candidate.get_absolute_url())
    return render(request, 'reserve/recommend_form.html', {
        'form': form, 'candidate': candidate,
    })


@reserve_editor_required
def recommendation_status(request, pk):
    recommendation = get_object_or_404(ReserveRecommendation, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('status', '')
        if status in RecommendationStatus.values:
            services.update_recommendation_status(
                recommendation, status,
                comment=request.POST.get('comment', ''), user=request.user,
            )
            messages.success(request, 'Результат по рекомендации сохранён.')
    return redirect(recommendation.candidate.get_absolute_url())


# --- публичная часть: анкета кандидата по персональной ссылке ---

def apply_form(request, token):
    """Анкета кандидата. Доступна только по действующей ссылке."""
    invite = ReserveInvite.objects.filter(token=token).first()
    if invite is None or not invite.is_open:
        return render(request, 'reserve/apply_expired.html', status=404)
    form = ReserveApplyForm(
        request.POST or None, request.FILES or None, instance=invite.candidate,
    )
    if request.method == 'POST' and form.is_valid():
        services.accept_application(invite, form)
        return render(request, 'reserve/apply_done.html', {
            'is_edit': invite.is_edit_link,
        })
    return render(request, 'reserve/apply.html', {
        'form': form, 'invite': invite, 'is_edit': invite.is_edit_link,
        'direction_groups': json.dumps(services.direction_groups_map()),
        'mark_optional': True,
    })
