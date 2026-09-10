from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.interns import services
from apps.interns.forms import (
    GrantAccessForm, InternEvaluationForm, InternForm, ProfileApplyForm,
    ResumeBankApplyForm, TalentReserveApplyForm, TalentReserveForm,
)
from apps.interns.models import (
    Intern, InternEvaluation, InternStatus, ProfileFormLink,
    ProfileFormSubmission, TalentReserveCandidate,
)
from apps.teams.forms import ROLE_BY_SPECIALIZATION, InternProjectAddForm
from apps.teams.models import TeamMember, TeamRole
from apps.training.models import Specialization


def lead_ids() -> set:
    """Тимлиды — сотрудники на зарплате, в списке стажёров их нет."""
    from apps.teams.selectors import lead_intern_ids

    return lead_intern_ids()


def _attach_current_projects(interns) -> None:
    """Над каким проектом сейчас работает — один запрос вместо N+1."""
    ids = [i.pk for i in interns]
    if not ids:
        return
    memberships = (
        TeamMember.objects.filter(
            intern_id__in=ids, status=TeamMember.Status.ACTIVE,
            project__isnull=False,
        )
        .select_related('project')
        .order_by('project__name')
    )
    by_intern = {}
    for member in memberships:
        by_intern.setdefault(member.intern_id, []).append(member.project)
    for intern in interns:
        intern.current_projects = by_intern.get(intern.pk, [])


@login_required
def intern_list(request):
    qs = (
        Intern.objects.active()
        .exclude(pk__in=lead_ids())
        .select_related('specialization', 'training_group', 'team_lead')
    )
    params = request.GET
    search = params.get('q', '').strip()
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(telegram__icontains=search),
        )
    if params.get('specialization'):
        qs = qs.filter(specialization_id=params['specialization'])
    if params.get('city'):
        qs = qs.filter(city=params['city'])
    busy_ids = set(
        TeamMember.objects.filter(
            status=TeamMember.Status.ACTIVE, intern__isnull=False,
        ).values_list('intern_id', flat=True),
    )
    if params.get('availability') == 'free':
        qs = qs.exclude(pk__in=busy_ids)
    elif params.get('availability') == 'busy':
        qs = qs.filter(pk__in=busy_ids)

    paginator = Paginator(qs, 50)
    page = paginator.get_page(params.get('page'))
    for intern in page.object_list:
        intern.is_busy = intern.pk in busy_ids
    _attach_current_projects(page.object_list)
    from apps.resources.services import interns_summary
    base_params = params.copy()
    base_params.pop('specialization', None)
    base_params.pop('page', None)
    context = {
        'page': page,
        'params': params,
        'base_qs': base_params.urlencode(),
        'balance': interns_summary(),
        'specializations': Specialization.objects.all(),
        'cities': Intern.objects.active().exclude(city='')
                  .values_list('city', flat=True).distinct().order_by('city'),
        'profile_link': services.active_profile_form_link(),
        'profile_link_ttls': PROFILE_LINK_TTL_CHOICES,
        'answers_count': ProfileFormSubmission.objects.count(),
    }
    return render(request, 'interns/list.html', context)


# Сроки жизни ссылки на анкету: значение для формы → подпись
PROFILE_LINK_TTL_CHOICES = [
    ('1', 'Сутки'),
    ('3', '3 дня'),
    ('7', '7 дней'),
    ('30', '30 дней'),
    ('', 'Без срока'),
]


@login_required
def profile_link_create(request):
    """Выпустить новую ссылку на публичную анкету (старая перестаёт работать)."""
    if request.method == 'POST':
        raw_ttl = request.POST.get('ttl_days', '')
        ttl_days = int(raw_ttl) if raw_ttl.isdigit() else None
        link = services.issue_profile_form_link(request.user, ttl_days)
        term = f'на {ttl_days} дн.' if ttl_days else 'без срока'
        messages.success(
            request,
            f'Новая ссылка на анкету создана ({term}), прежняя больше не '
            f'открывается: {request.build_absolute_uri(link.get_absolute_url())}',
        )
    return redirect('interns:list')


@login_required
def profile_link_answers(request):
    """Журнал заполнений анкеты — кто и по какой ссылке её прошёл."""
    submissions = (
        ProfileFormSubmission.objects
        .select_related('intern', 'link')
        .order_by('-created_at')
    )
    token = request.GET.get('link', '')
    if token:
        submissions = submissions.filter(link__token=token)
    paginator = Paginator(submissions, 50)
    return render(request, 'interns/profile_link_answers.html', {
        'page': paginator.get_page(request.GET.get('page')),
        'links': ProfileFormLink.objects.all()[:50],
        'token': token,
        'total': paginator.count,
    })


@login_required
def profile_link_disable(request):
    """Отключить действующую ссылку, не выпуская новую."""
    if request.method == 'POST':
        link = services.active_profile_form_link()
        if link is not None:
            link.deactivate()
            messages.success(request, 'Ссылка на анкету отключена.')
    return redirect('interns:list')


@login_required
def intern_detail(request, pk):
    intern = get_object_or_404(
        Intern.objects.select_related(
            'specialization', 'training_group', 'team_lead',
        ),
        pk=pk,
    )
    memberships = intern.team_memberships.select_related('project')
    active_memberships = [
        m for m in memberships if m.status == TeamMember.Status.ACTIVE
    ]
    past_memberships = [
        m for m in memberships if m.status == TeamMember.Status.LEFT
    ]
    roles = {m.role for m in active_memberships}
    is_lead = TeamRole.TEAM_LEAD in roles
    is_pm = TeamRole.PROJECT_MANAGER in roles
    if is_lead:
        kind, kind_tone = 'Тимлид направления', 'orange'
    else:
        # ПМ — тоже стажёр, а не отдельная категория: его роль и так
        # видна по проектам ниже и по направлению «PM» в шапке.
        kind, kind_tone = 'Стажёр', 'gray'

    context = {
        'intern': intern,
        'is_lead': is_lead,
        'kind': kind,
        'kind_tone': kind_tone,
        'lead_projects': [
            m for m in active_memberships if m.role == TeamRole.TEAM_LEAD
        ],
        'active_memberships': active_memberships,
        'past_memberships': past_memberships,
        'projects_count': len(active_memberships) + len(past_memberships),
        'evaluations': intern.evaluations.select_related('project', 'evaluator'),
        'criteria': InternEvaluation.CRITERIA,
        'is_pm': is_pm,
    }
    return render(request, 'interns/detail.html', context)


@login_required
def intern_project_add(request, pk):
    """Добавить стажёра на проект прямо с его карточки."""
    intern = get_object_or_404(Intern, pk=pk)
    form = InternProjectAddForm(
        request.POST or None, instance=TeamMember(intern=intern),
    )
    if request.method == 'POST' and form.is_valid():
        member = form.save(commit=False)
        member.group = getattr(member.project, 'group', None)
        spec = intern.specialization
        member.role = ROLE_BY_SPECIALIZATION.get(
            spec.name if spec else '', TeamRole.OTHER,
        )
        member.joined_at = timezone.localdate()
        member.save()
        if intern.status in (InternStatus.WAITING, InternStatus.READY):
            intern.status = InternStatus.ACTIVE
            intern.save(update_fields=['status', 'updated_at'])
        messages.success(
            request, f'{intern.full_name} добавлен(а) в «{member.project.name}».',
        )
        return redirect(intern.get_absolute_url())
    return render(request, 'interns/project_add_form.html', {
        'form': form, 'intern': intern,
    })


@login_required
def intern_project_remove(request, pk, member_pk):
    """Убрать стажёра с проекта прямо с его карточки."""
    intern = get_object_or_404(Intern, pk=pk)
    member = get_object_or_404(TeamMember, pk=member_pk, intern=intern)
    if request.method == 'POST':
        name = member.project.name if member.project_id else 'проекта'
        member.delete()
        messages.success(request, f'Убран(а) с «{name}».')
    return redirect(intern.get_absolute_url())


@login_required
def intern_create(request):
    form = InternForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        intern = form.save()
        messages.success(request, f'Стажёр {intern.full_name} добавлен(а).')
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/form.html', {'form': form, 'title': 'Новый стажёр'},
    )


@login_required
def intern_update(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    form = InternForm(request.POST or None, instance=intern)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Карточка стажёра обновлена.')
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/form.html',
        {'form': form, 'title': f'Редактирование: {intern.full_name}'},
    )


@login_required
def evaluation_add(request, pk):
    intern = get_object_or_404(Intern, pk=pk)
    form = InternEvaluationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        evaluation = form.save(commit=False)
        evaluation.intern = intern
        evaluation.evaluator = request.user
        services.add_evaluation(evaluation)
        messages.success(
            request,
            f'Оценка сохранена. Средний рейтинг: {intern.rating}.',
        )
        return redirect(intern.get_absolute_url())
    return render(
        request, 'interns/evaluation_form.html',
        {'form': form, 'intern': intern, 'title': f'Оценка: {intern.full_name}'},
    )


@login_required
def intern_delete(request, pk):
    """Удаление человека из базы вместе с участием в командах."""
    intern = get_object_or_404(Intern, pk=pk)
    if request.method == "POST":
        name = intern.full_name
        teams = intern.team_memberships.count()
        intern.delete()
        note = f" и снят(а) с проектов: {teams}" if teams else ""
        messages.success(request, f"{name} удалён(а) из базы{note}.")
        return redirect("interns:list")
    return redirect(intern.get_absolute_url())


@login_required
def grant_pm_access(request, pk):
    """Выдать (или сбросить) доступ ПМа в его портал — логин по телефону."""
    from apps.accounts.models import User

    intern = get_object_or_404(Intern, pk=pk)
    initial = {'username': intern.user.username if intern.user else intern.phone}
    form = GrantAccessForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        if intern.user:
            user = intern.user
            user.username = username
        else:
            user = User(username=username, role=User.Role.PROJECT_MANAGER)
        user.role = User.Role.PROJECT_MANAGER
        user.phone = intern.phone
        user.set_password(password)
        user.save()
        if not intern.user_id:
            intern.user = user
            intern.save(update_fields=['user', 'updated_at'])
        messages.success(request, f'Доступ выдан: логин «{username}».')
        return redirect(intern.get_absolute_url())
    return render(request, 'interns/grant_access_form.html', {
        'form': form, 'intern': intern,
    })


def _flagged_list(request, field, title):
    """Банк резюме — включая тимлидов, в отличие от общего списка
    стажёров (там тимлиды — уже «сотрудники»)."""
    people = (
        Intern.objects.active().filter(**{field: True})
        .select_related('specialization').order_by('full_name')
    )
    return render(request, 'interns/flagged_list.html', {
        'people': people, 'title': title,
    })


@login_required
def reserve_list(request):
    """Резерв кадров — отдельный пул, не привязан к карточкам стажёров."""
    candidates = TalentReserveCandidate.objects.active().select_related('specialization')
    return render(request, 'interns/reserve_list.html', {
        'candidates': candidates,
    })


@login_required
def reserve_create(request):
    initial = {
        'full_name': request.GET.get('full_name', ''),
        'phone': request.GET.get('phone', ''),
        'email': request.GET.get('email', ''),
        'city': request.GET.get('city', ''),
    }
    form = TalentReserveForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        candidate = form.save()
        messages.success(request, f'«{candidate.full_name}» добавлен(а) в резерв.')
        return redirect('interns:reserve')
    return render(request, 'interns/reserve_form.html', {
        'form': form, 'title': 'Новый кандидат в резерве',
    })


@login_required
def reserve_update(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    form = TalentReserveForm(request.POST or None, instance=candidate)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Кандидат обновлён.')
        return redirect('interns:reserve')
    return render(request, 'interns/reserve_form.html', {
        'form': form, 'title': f'Резерв: {candidate.full_name}',
    })


@login_required
def reserve_delete(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    if request.method == 'POST':
        name = candidate.full_name
        candidate.delete()
        messages.success(request, f'{name} удалён(а) из резерва.')
    return redirect('interns:reserve')


@login_required
def reserve_set_priority(request, pk):
    candidate = get_object_or_404(TalentReserveCandidate, pk=pk)
    if request.method == 'POST':
        raw = request.POST.get('priority', '')
        if raw.isdigit():
            candidate.priority = int(raw)
            candidate.save(update_fields=['priority', 'updated_at'])
    return redirect('interns:reserve')


@login_required
def resume_bank_list(request):
    return _flagged_list(request, 'in_resume_bank', 'Банк резюме')


@login_required
def graduates_list(request):
    """Стажёры с завершённых проектов — кандидаты в резерв/банк резюме."""
    people = services.graduated_interns()
    return render(request, 'interns/graduates_list.html', {
        'people': people, 'title': 'Выпускники',
    })


def resume_bank_apply(request):
    """Публичная анкета «Банк резюме» — без входа в систему.

    По телефону ищем уже существующего стажёра, чтобы не плодить
    дубли, если человек уже есть в базе. Одна анкета на браузер —
    после отправки повторно её не откроешь (защита от спама).
    """
    if request.session.get('resume_bank_submitted'):
        return render(request, 'interns/resume_bank_apply_done.html')
    form = ResumeBankApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        intern = Intern.objects.filter(phone=phone).first()
        if intern is None:
            intern = form.save(commit=False)
        else:
            intern.full_name = form.cleaned_data['full_name']
            intern.email = form.cleaned_data['email']
            intern.specialization = form.cleaned_data['specialization']
        intern.in_resume_bank = True
        intern.save()
        request.session['resume_bank_submitted'] = True
        return render(request, 'interns/resume_bank_apply_done.html')
    return render(request, 'interns/resume_bank_apply.html', {'form': form})


def profile_link_expired(request):
    """Старый постоянный адрес анкеты — только сообщение, что ссылка мертва."""
    return render(request, 'interns/profile_apply_expired.html', status=404)


def profile_apply(request, token):
    """Публичная анкета: стажёр сам заполняет/обновляет свой профиль.

    Открывается только по действующей ссылке (`token`): постоянного
    адреса у анкеты нет, ПМ выпускает новую ссылку и старые умирают.

    Сначала ищем по телефону. У многих текущих записей телефон ещё не
    заполнен (карточку когда-то завели по одному ФИО) — тогда, чтобы не
    плодить дубль, ищем среди записей без телефона точное совпадение по
    имени. Если и это не помогло — считаем человека новым. Одна анкета
    на браузер и ссылку — после отправки повторно её не откроешь
    (защита от спама).
    """
    link = ProfileFormLink.objects.filter(token=token).first()
    if link is None or not link.is_open:
        return render(request, 'interns/profile_apply_expired.html', status=404)
    session_key = f'profile_submitted:{token}'
    if request.session.get(session_key):
        return render(request, 'interns/profile_apply_done.html')
    form = ProfileApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        full_name = form.cleaned_data['full_name']
        intern = Intern.objects.filter(phone=phone).first()
        if intern is None:
            intern = Intern.objects.filter(
                phone='', full_name__iexact=full_name,
            ).first()
        is_new = intern is None
        if is_new:
            intern = form.save(commit=False)
        else:
            for field in ProfileApplyForm.Meta.fields:
                setattr(intern, field, form.cleaned_data[field])
        intern.save()
        ProfileFormLink.objects.filter(pk=link.pk).update(
            submissions=models.F('submissions') + 1,
        )
        ProfileFormSubmission.objects.create(
            link=link, intern=intern, full_name=intern.full_name,
            phone=intern.phone, is_new=is_new,
        )
        request.session[session_key] = True
        return render(request, 'interns/profile_apply_done.html')
    return render(request, 'interns/profile_apply.html', {'form': form})


def talent_reserve_apply(request):
    """Публичная анкета «Резерв кадров» — без входа в систему.

    Тот же принцип поиска, что и в анкете профиля: сначала точное
    совпадение по телефону, иначе — по ФИО среди записей без телефона.
    Одна анкета на браузер — после отправки повторно её не откроешь
    (защита от спама).
    """
    if request.session.get('talent_reserve_submitted'):
        return render(request, 'interns/reserve_apply_done.html')
    form = TalentReserveApplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        phone = form.cleaned_data['phone']
        full_name = form.cleaned_data['full_name']
        candidate = TalentReserveCandidate.objects.filter(phone=phone).first()
        if candidate is None:
            candidate = TalentReserveCandidate.objects.filter(
                phone='', full_name__iexact=full_name,
            ).first()
        if candidate is None:
            candidate = form.save(commit=False)
        else:
            for field in TalentReserveApplyForm.Meta.fields:
                setattr(candidate, field, form.cleaned_data[field])
        candidate.save()
        request.session['talent_reserve_submitted'] = True
        return render(request, 'interns/reserve_apply_done.html')
    return render(request, 'interns/reserve_apply.html', {'form': form})
