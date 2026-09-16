"""Разбор сообщения от IT-академии со списком групп.

Академия присылает текст такого вида — его и понимаем:

    🎨 Design
    * 39 группа — старт: 09.06.2026 · конец: 06.10.2026 — 4 студента
    * 43 группа — старт: 19.08.2026 · конец: 03.02.2027 — 5–7 студентов
    * 48 группа — старт: 28.09.2026 · конец: 11.03.2027 — количество пока неизвестно

Строка без «группа» — заголовок направления, строки ниже относятся к нему.
Группа определяется парой «направление + номер»: повторная вставка того
же сообщения обновляет даты и численность, а не плодит дубли.
"""
import datetime
import re
from dataclasses import dataclass, field

from apps.training.models import Specialization, TrainingGroup

# Как академия называет направления → как они называются у нас
ALIASES = {
    'design': 'UX/UI', 'дизайн': 'UX/UI', 'ui/ux': 'UX/UI', 'ux/ui': 'UX/UI',
    'uxui': 'UX/UI', 'ux': 'UX/UI',
    'flutter': 'Mobile', 'mobile': 'Mobile', 'мобильная разработка': 'Mobile',
    'frontend': 'Frontend', 'фронтенд': 'Frontend',
    'backend': 'Backend', 'бэкенд': 'Backend', 'python': 'Backend',
    'qa': 'Testing/QA', 'тестирование': 'Testing/QA',
    'devops': 'DevOps', 'pm': 'PM',
}

GROUP_RE = re.compile(
    r'(?P<number>\d+)\s*групп\w*'
    r'.*?старт\w*\s*:?\s*(?P<start>\d{1,2}\.\d{1,2}\.\d{4})'
    r'.*?конец\w*\s*:?\s*(?P<end>\d{1,2}\.\d{1,2}\.\d{4})'
    r'\s*(?:[—–-]\s*(?P<students>.*))?$',
    re.IGNORECASE,
)
RANGE_RE = re.compile(r'(\d+)\s*[–—-]\s*(\d+)')
NUMBER_RE = re.compile(r'\d+')


@dataclass
class ParsedGroup:
    line: str
    direction_name: str
    specialization: Specialization | None
    number: str = ''
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    students_count: int | None = None
    students_note: str = ''
    errors: list[str] = field(default_factory=list)
    existing: TrainingGroup | None = None
    changes: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        if self.errors:
            return 'error'
        if self.existing is None:
            return 'create'
        return 'update' if self.changes else 'same'


def find_specialization(name: str) -> Specialization | None:
    cleaned = name.strip().lower()
    by_name = {spec.name.lower(): spec for spec in Specialization.objects.all()}
    if cleaned in by_name:
        return by_name[cleaned]
    alias = ALIASES.get(cleaned)
    if alias:
        return by_name.get(alias.lower())
    return None


def _date(raw: str) -> datetime.date:
    day, month, year = (int(part) for part in raw.split('.'))
    return datetime.date(year, month, day)


def _students(raw: str) -> tuple[int | None, str]:
    """«8 студентов» → 8; «5–7» → 5 и пометка; «неизвестно» → None."""
    text = (raw or '').strip().rstrip('.')
    if not text:
        return None, ''
    found = RANGE_RE.search(text)
    if found:
        # Планируем по нижней границе, а как прислали — сохраняем
        return int(found.group(1)), text
    found = NUMBER_RE.search(text)
    if found:
        plain = re.fullmatch(r'\d+\s*студент\w*', text, re.IGNORECASE)
        return int(found.group()), '' if plain else text
    return None, text


def _clean_header(line: str) -> str:
    """Убираем эмодзи и маркеры: «⚙️Backend» → «Backend»."""
    return re.sub(r'[^\w\s/+\-]', '', line).strip()


def parse(text: str) -> list[ParsedGroup]:
    rows = []
    direction_name, specialization = '', None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        body = line.lstrip('*•-–— \t')
        match = GROUP_RE.search(body)
        if match is None:
            if re.search(r'групп', body, re.IGNORECASE):
                rows.append(ParsedGroup(
                    line=line, direction_name=direction_name,
                    specialization=specialization,
                    errors=['Не разобрал строку: нужны номер группы, «старт» и «конец».'],
                ))
                continue
            direction_name = _clean_header(body)
            specialization = find_specialization(direction_name)
            continue

        row = ParsedGroup(
            line=line, direction_name=direction_name,
            specialization=specialization, number=match.group('number'),
        )
        if not direction_name:
            row.errors.append('Нет заголовка направления над группой.')
        elif specialization is None:
            row.errors.append(
                f'Направление «{direction_name}» не найдено в справочнике.',
            )
        try:
            row.start_date = _date(match.group('start'))
            row.end_date = _date(match.group('end'))
        except ValueError:
            row.errors.append('Неверная дата.')
        if row.start_date and row.end_date and row.end_date < row.start_date:
            row.errors.append('Конец раньше старта.')
        row.students_count, row.students_note = _students(match.group('students'))
        rows.append(row)

    for row in rows:
        if row.errors:
            continue
        row.existing = TrainingGroup.objects.filter(
            specialization=row.specialization, number=row.number,
        ).first()
        if row.existing:
            row.changes = _diff(row.existing, row)
    return rows


def _diff(group: TrainingGroup, row: ParsedGroup) -> list[str]:
    changes = []
    pairs = [
        ('старт', group.start_date, row.start_date),
        ('конец', group.end_date, row.end_date),
        ('студентов', group.students_count, row.students_count),
        ('уточнение', group.students_note, row.students_note),
    ]
    for label, old, new in pairs:
        if old != new:
            changes.append(label)
    return changes


def apply(rows: list[ParsedGroup]) -> dict:
    """Сохраняет разобранные группы. Строки с ошибками пропускает."""
    result = {'created': 0, 'updated': 0, 'same': 0, 'skipped': 0}
    for row in rows:
        action = row.action
        if action == 'error':
            result['skipped'] += 1
            continue
        if action == 'same':
            result['same'] += 1
            continue
        group = row.existing or TrainingGroup(
            specialization=row.specialization, number=row.number,
        )
        group.start_date = row.start_date
        group.end_date = row.end_date
        group.students_count = row.students_count
        group.students_note = row.students_note
        group.save()
        result['created' if action == 'create' else 'updated'] += 1
    return result
