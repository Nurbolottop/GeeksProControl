from django import forms

from apps.interns.models import Intern, InternEvaluation


class InternForm(forms.ModelForm):
    class Meta:
        model = Intern
        fields = [
            'full_name', 'phone', 'email', 'telegram', 'city', 'branch',
            'specialization', 'education_end_date',
            'internship_start_date', 'status', 'comment',
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


class GrantAccessForm(forms.Form):
    """Выдать/сбросить доступ ПМу — логином служит телефон."""

    username = forms.CharField(label='Телефон (логин)', max_length=150)
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput)


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
