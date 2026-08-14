from django import forms

from apps.interns.models import Intern, InternEvaluation


class InternForm(forms.ModelForm):
    class Meta:
        model = Intern
        fields = [
            'full_name', 'phone', 'email', 'city', 'branch',
            'specialization', 'training_group', 'education_end_date',
            'internship_start_date', 'status', 'team_lead', 'comment',
        ]
        widgets = {
            'education_end_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'internship_start_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }


class InternEvaluationForm(forms.ModelForm):
    class Meta:
        model = InternEvaluation
        fields = [
            'project', 'hard_skills', 'quality', 'speed', 'responsibility',
            'communication', 'teamwork', 'independence', 'comment',
        ]
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 2}),
        }
