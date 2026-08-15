from django import forms

from apps.projects.models import Project, ProjectStage


class ProjectForm(forms.ModelForm):
    """Форма создания/редактирования проекта.

    При переносе плановой даты завершения обязательно требуется причина
    (ТЗ §21): она пишется в историю изменений.
    """

    change_reason = forms.CharField(
        label='Причина переноса срока', required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    class Meta:
        model = Project
        fields = [
            'name', 'client', 'city', 'flow', 'project_type', 'description',
            'contract_date', 'start_date', 'planned_end_date',
            'status', 'current_stage', 'priority', 'progress',
            'project_manager', 'team_lead', 'head_comment',
            'github_url', 'figma_url', 'staging_url', 'production_url',
            'domain', 'is_favorite',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'head_comment': forms.Textarea(attrs={'rows': 2}),
            'contract_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'start_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'planned_end_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk and 'planned_end_date' in self.changed_data:
            old_value = Project.objects.get(pk=self.instance.pk).planned_end_date
            if old_value and not cleaned.get('change_reason', '').strip():
                self.add_error(
                    'change_reason',
                    'При переносе срока обязательно укажите причину.',
                )
        return cleaned


class StageUpdateForm(forms.ModelForm):
    """Инлайн-редактирование этапа в карточке проекта."""

    class Meta:
        model = ProjectStage
        fields = ['status', 'progress', 'deadline', 'responsible', 'comment']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.TextInput(),
        }
