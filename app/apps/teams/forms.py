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
        fields = ['intern', 'comment']
        labels = {'intern': 'Участник'}
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
        """Сколько ещё проектов у человека — предупреждение при распылении."""
        if not self.is_valid():
            return None
        intern = self.cleaned_data.get('intern')
        if not intern:
            return None
        others = TeamMember.objects.filter(
            intern=intern, status=TeamMember.Status.ACTIVE,
        ).exclude(pk=self.instance.pk).count()
        if others >= 2:
            return (
                f'{intern.full_name} уже занят(а) на {others} проектах — '
                f'этот будет третьим.'
            )
        return None


class TeamMemberEditForm(TeamMemberForm):
    """Редактирование участника: добавляются статус и даты участия.

    В списке — только люди подходящего направления: если меняем PM,
    предлагаются PM, если бэкендера — бэкендеры.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        member = self.instance
        if not member.pk:
            return
        # Направление, из которого выбираем замену
        spec_by_role = {
            value: key for key, value in ROLE_BY_SPECIALIZATION.items()
        }
        spec_name = spec_by_role.get(member.role)
        if member.role == TeamRole.TEAM_LEAD and member.intern_id:
            # Тимлида меняем на человека того же направления
            spec = member.intern.specialization
            spec_name = spec.name if spec else None
        if spec_name:
            queryset = self.fields['intern'].queryset.filter(
                specialization__name=spec_name,
            )
            # Текущий участник всегда остаётся в списке
            if member.intern_id:
                queryset = queryset | self.fields['intern'].queryset.filter(
                    pk=member.intern_id,
                )
            self.fields['intern'].queryset = queryset.distinct()
            self.fields['intern'].help_text = f'Показаны только: {spec_name}'

    class Meta(TeamMemberForm.Meta):
        fields = [
            'intern', 'joined_at', 'left_at', 'status', 'comment',
        ]
        widgets = {
            'joined_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'left_at': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }
