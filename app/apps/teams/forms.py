from django import forms

from apps.teams import services
from apps.teams.models import TeamMember


class TeamMemberForm(forms.ModelForm):
    """Добавление участника в команду проекта.

    Люди GeeksPro (кураторы, PM, тимлиды, стажёры) — единый список,
    роль в проекте задаётся отдельным полем. При суммарной загрузке > 100%
    форма не блокирует сохранение, но показывает предупреждение (ТЗ §11).
    """

    class Meta:
        model = TeamMember
        fields = [
            'intern', 'role', 'workload',
            'joined_at', 'left_at', 'status', 'comment',
        ]
        labels = {'intern': 'Участник'}
        widgets = {
            'joined_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'left_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['intern']
        field.required = True
        field.queryset = field.queryset.filter(is_archived=False).order_by('full_name')
        field.empty_label = 'Выберите человека'

    def overload_warning(self) -> str | None:
        """Текст предупреждения о перегрузе после валидации формы."""
        if not self.is_valid():
            return None
        intern = self.cleaned_data.get('intern')
        if not intern:
            return None
        total = services.person_workload(
            intern=intern, exclude_pk=self.instance.pk,
        ) + self.cleaned_data.get('workload', 0)
        if total > 100:
            return f'Внимание: суммарная загрузка {intern.full_name} составит {total}%.'
        return None
