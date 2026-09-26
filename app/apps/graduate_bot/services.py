"""Бизнес-логика бота-выпускника — без обращений к Telegram API, чтобы
можно было полностью протестировать обычными django-тестами
(исключение — notify_resume_bank_decision: она шлёт сообщение, но сама
Telegram-логика в ней однострочная и мокается в тестах).

Диалог (реализован в apps/graduate_bot/bot.py): выпускник вводит ФИО,
подтверждает личность номером телефона, затем выбирает — продолжить
стажировку (сам выбирает свободный проект и добавляется в команду) или
уйти в банк резюме.
"""
import logging
import re

from apps.interns.models import Intern, ResumeBankStatus
from apps.projects.models import Project, ProjectStageKey, ProjectStatus
from apps.teams.models import TeamMember, TeamRole

logger = logging.getLogger(__name__)

# Этапы «до разработки включительно» — на этих этапах команда ещё
# набирается или дорабатывается, есть смысл предлагать проект выпускнику.
# Со «Тестового сервера» и дальше команда уже укомплектована для сдачи.
ROOM_STAGES = [
    ProjectStageKey.NEW, ProjectStageKey.DOCUMENTS, ProjectStageKey.REQUIREMENTS,
    ProjectStageKey.TEAM_FORMING, ProjectStageKey.DESIGN,
    ProjectStageKey.BACKEND, ProjectStageKey.FRONTEND, ProjectStageKey.MOBILE_DEV,
]
MAX_TEAM_SIZE_WITH_ROOM = 4


def find_graduates(name: str, limit: int = 5) -> list[Intern]:
    """Выпускники «на проверке» или «не хочет продолжать» с похожим ФИО."""
    from apps.interns.services import graduated_interns

    name = name.strip()
    if not name:
        return []
    return [
        intern for intern in graduated_interns()
        if name.lower() in intern.full_name.lower()
    ][:limit]


def _digits(value: str) -> str:
    return re.sub(r'\D', '', value or '')


def phone_matches(intern: Intern, raw_phone: str) -> bool:
    """Сверка по последним 9 цифрам — не важно, как записан код страны
    (+996, 996, 0 или вообще без него)."""
    entered = _digits(raw_phone)
    stored = _digits(intern.phone)
    if len(entered) < 9 or len(stored) < 9:
        return False
    return entered[-9:] == stored[-9:]


def remember_chat_id(intern: Intern, chat_id: int) -> None:
    """Запоминаем chat_id — нужен, чтобы потом писать выпускнику
    проактивно (решение по банку резюме), а не только в ответ."""
    if intern.telegram_chat_id == chat_id:
        return
    intern.telegram_chat_id = chat_id
    intern.save(update_fields=['telegram_chat_id', 'updated_at'])


def completed_projects(intern: Intern) -> list[TeamMember]:
    """Членства в командах завершённых проектов — для поздравительного
    сообщения («вы завершили проекты: ...»)."""
    return list(
        TeamMember.objects.filter(
            intern=intern, status=TeamMember.Status.LEFT,
            project__status=ProjectStatus.COMPLETED,
        )
        .select_related('project')
        .order_by('-project__actual_end_date', '-left_at'),
    )


def submit_to_resume_bank(intern: Intern, chat_id: int) -> None:
    """Выпускник подтвердил регистрацию на geeks.kg через бота — заявка
    уходит руководителю на проверку (apps.interns.views.resume_bank_approve/
    resume_bank_revise)."""
    from apps.audit.services import log as audit_log

    remember_chat_id(intern, chat_id)
    intern.in_resume_bank = True
    intern.resume_bank_status = ResumeBankStatus.PENDING
    intern.resume_bank_comment = ''
    intern.save(update_fields=[
        'in_resume_bank', 'resume_bank_status', 'resume_bank_comment', 'updated_at',
    ])
    audit_log(intern, 'Заявка в банк резюме отправлена', reason='бот-выпускник')


def notify_resume_bank_decision(intern: Intern, *, approved: bool, comment: str = '') -> None:
    """Сообщаем выпускнику решение руководителя по его заявке в банк
    резюме. Вызывается из админки (apps.interns.views), в отдельном от
    поллинга бота процессе — это нормально, отправка сообщения не
    требует владения long-poll соединением (конфликт 409 бывает только
    у getUpdates)."""
    if not intern.telegram_chat_id:
        return
    if approved:
        text = (
            f'🎉 Поздравляем, {intern.full_name}! Ваше резюме приняли — '
            'оно опубликовано в банке резюме GeeksPro.'
        )
    else:
        text = (
            'Ваше резюме нужно доработать.\n\n'
            f'Комментарий от руководителя:\n{comment}\n\n'
            'Когда исправите — сообщите руководителю GeeksPro.'
        )
    try:
        from apps.graduate_bot.bot import bot

        bot.send_message(intern.telegram_chat_id, text)
    except Exception:
        logger.exception('Не удалось отправить решение по банку резюме в Telegram (intern=%s)', intern.pk)


def eligible_projects() -> list[Project]:
    """Проекты, где ещё есть место: этап не дальше разработки и в
    команде меньше 4 активных участников (правило заказчика)."""
    candidates = (
        Project.objects.filter(
            status=ProjectStatus.ACTIVE, current_stage__in=ROOM_STAGES,
        )
        .order_by('name')
    )
    return [
        project for project in candidates
        if project.team_members.filter(status=TeamMember.Status.ACTIVE).count()
        < MAX_TEAM_SIZE_WITH_ROOM
    ]


def join_graduate_to_project(intern: Intern, project: Project, *, source: str = 'бот-выпускник') -> TeamMember:
    """Выпускник сам выбрал проект — добавляем в команду, снимаем статус
    выпускника, оставляем след в истории (как при ручном переводе,
    apps/interns/views.py::intern_project_add)."""
    from django.utils import timezone

    from apps.audit.services import log as audit_log
    from apps.interns.models import InternStatus
    from apps.teams.forms import ROLE_BY_SPECIALIZATION

    spec = intern.specialization
    member = TeamMember.objects.create(
        project=project, intern=intern,
        group=getattr(project, 'group', None),
        role=ROLE_BY_SPECIALIZATION.get(spec.name if spec else '', TeamRole.OTHER),
        status=TeamMember.Status.ACTIVE,
        joined_at=timezone.localdate(),
    )
    update_fields = []
    if intern.status != InternStatus.ACTIVE:
        intern.status = InternStatus.ACTIVE
        update_fields.append('status')
    if intern.graduate_status:
        audit_log(
            intern, 'Статус выпускника снят',
            old_value=intern.get_graduate_status_display(),
            reason=f'{source}: сам выбрал(а) проект «{project.name}»',
        )
        intern.graduate_status = ''
        update_fields.append('graduate_status')
    if update_fields:
        intern.save(update_fields=[*update_fields, 'updated_at'])
    return member


def team_lead_contact(project: Project, intern: Intern) -> Intern | None:
    """Тимлид своего направления на этом проекте — кому писать после
    добавления в команду. У тимлида направление — по его собственной
    специализации (как apps.lead_portal.services.lead_own_role), не по
    роли TeamMember — она у всех тимлидов одна и та же, 'team_lead'."""
    from apps.teams.forms import ROLE_BY_SPECIALIZATION

    own_role = (
        ROLE_BY_SPECIALIZATION.get(intern.specialization.name)
        if intern.specialization else None
    )
    leads = (
        TeamMember.objects.filter(
            project=project, role=TeamRole.TEAM_LEAD, status=TeamMember.Status.ACTIVE,
        )
        .exclude(intern__isnull=True)
        .select_related('intern__specialization')
    )
    if own_role:
        for member in leads:
            spec = member.intern.specialization
            if spec and ROLE_BY_SPECIALIZATION.get(spec.name) == own_role:
                return member.intern
    first = leads.first()
    return first.intern if first else None
