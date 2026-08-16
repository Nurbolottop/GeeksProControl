from django import forms
from django.utils import timezone

from apps.teams import services
from apps.teams.models import TeamMember, TeamRole


# Направление человека → его роль в команде
ROLE_BY_SPECIALIZATION = {
    'Backend': TeamRole.BACKEND,
    'Frontend': TeamRole.FRONTEND,
    'UX/UI': TeamRole.UXUI,
    'Mobile': TeamRole.MOBILE,
    'Testing/QA': TeamRole.QA,
    'PM': TeamRole.PROJECT_MANAGER,
    'DevOps': TeamRole.OTHER,
}


class TeamMemberForm(forms.ModelForm):
    """Добавление участника в команду.

    Роль не выбирается — она берётся из направления человека
    (Backend, Frontend, UX/UI…). Отдельной галочкой отмечается тимлид.
    При суммарной загрузке > 100% показывается предупреждение (ТЗ §11).
    """

    is_lead = forms.BooleanField(
        label='Тимлид направления', required=False,
        help_text='Отметьте, если человек ведёт направление в этой команде',
    )

    class Meta:
        model = TeamMember
        fields = ['intern', 'workload', 'comment']
        labels = {'intern': 'Участник', 'workload': 'Загрузка, %'}
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields['intern']
        field.required = True
        field.queryset = (
            field.queryset.filter(is_archived=False)
            .select_related('specialization').order_by('full_name')
        )
        field.empty_label = 'Выберите человека'
        if self.instance.pk:
            self.fields['is_lead'].initial = (
                self.instance.role == TeamRole.TEAM_LEAD
            )

    def save(self, commit=True):
        member = super().save(commit=False)
        if self.cleaned_data.get('is_lead'):
            member.role = TeamRole.TEAM_LEAD
        else:
            spec = member.intern.specialization if member.intern else None
            member.role = ROLE_BY_SPECIALIZATION.get(
                spec.name if spec else '', TeamRole.OTHER,
            )
        if not member.joined_at:
            member.joined_at = timezone.localdate()
        if commit:
            member.save()
        return member

    class Media:
        pass

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


class TeamMemberEditForm(TeamMemberForm):
    """Редактирование участника: добавляются статус и даты участия."""

    class Meta(TeamMemberForm.Meta):
        fields = [
            'intern', 'workload', 'joined_at', 'left_at', 'status', 'comment',
        ]
        widgets = {
            'joined_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'left_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }
