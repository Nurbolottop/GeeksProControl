"""Данные для вкладки «Графика»: дорожка этапов проекта."""
from apps.projects.models import ProjectStage, ProjectStageKey


def _shares(count: int) -> list[int]:
    """Доли этапов в процентах, в сумме ровно 100."""
    if not count:
        return []
    base = 100 // count
    shares = [base] * count
    for index in range(100 - base * count):
        shares[index] += 1
    return shares


def stage_roadmap(project) -> dict:
    """Этапы проекта дорожкой: что пройдено, где идём сейчас, что впереди.

    Служебный этап «Завершён» в дорожку не берём — он не работа, а
    финальный флажок в конце пути (как и в расчёте прогресса).
    """
    stages = [
        stage for stage in project.stages.all()
        if stage.key != ProjectStageKey.COMPLETED
    ]
    shares = _shares(len(stages))
    current_index = None
    for index, stage in enumerate(stages):
        if stage.status == ProjectStage.Status.IN_PROGRESS:
            current_index = index
            break
    if current_index is None:
        # ни один этап не в работе: встаём на первый незавершённый
        for index, stage in enumerate(stages):
            if stage.status != ProjectStage.Status.DONE:
                current_index = index
                break

    segments = []
    for index, stage in enumerate(stages):
        if stage.status == ProjectStage.Status.DONE:
            state = 'done'
        elif index == current_index:
            state = 'current'
        else:
            state = 'next'
        segments.append({
            'stage': stage,
            'title': stage.get_key_display(),
            'share': shares[index],
            'state': state,
            'is_current': index == current_index,
            'date': stage.end_date or stage.deadline,
            'date_is_plan': stage.end_date is None,
        })

    done = sum(1 for stage in stages if stage.status == ProjectStage.Status.DONE)
    return {
        'segments': segments,
        'total': len(stages),
        'done': done,
        'left': len(stages) - done,
        'percent': round(100 * done / len(stages)) if stages else 0,
        'current': segments[current_index] if current_index is not None else None,
    }
