from django import forms

from apps.teams import services
from apps.teams.models import TeamMember


class TeamMemberForm(forms.ModelForm):
    """Добавление участника в команду.

    При суммарной загрузке > 100% форма не блокирует сохранение,
    но предупреждение показывается пользователю (ТЗ §11).
    """

    class Meta:
        model = TeamMember
        fields = [
            'user', 'intern', 'role', 'workload',
            'joined_at', 'left_at', 'status', 'comment',
        ]
        widgets = {
            'joined_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'left_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def overload_warning(self) -> str | None:
        """Текст предупреждения о перегрузе после валидации формы."""
        if not self.is_valid():
            return None
        member = self.instance
        total = services.person_workload(
            user=self.cleaned_data.get('user'),
            intern=self.cleaned_data.get('intern'),
            exclude_pk=member.pk,
        ) + self.cleaned_data.get('workload', 0)
        if total > 100:
            name = (
                self.cleaned_data.get('user')
                and self.cleaned_data['user'].display_name
                or self.cleaned_data.get('intern')
                and self.cleaned_data['intern'].full_name
            )
            return f'Внимание: суммарная загрузка {name} составит {total}%.'
        return None
