from django import forms

from apps.training.models import TrainingGroup


class TrainingGroupForm(forms.ModelForm):
    """Группа академии: сколько учится и сколько ждём на стажировку."""

    class Meta:
        model = TrainingGroup
        fields = [
            'number', 'specialization', 'branch', 'status',
            'start_date', 'end_date',
            'students_count', 'wants_internship', 'expected_interns',
            'actual_interns', 'teacher', 'comment',
        ]
        widgets = {
            'number': forms.TextInput(attrs={'placeholder': 'Например: BE-14'}),
            'branch': forms.TextInput(attrs={'placeholder': 'Бишкек / Ош'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        data = super().clean()
        start, end = data.get('start_date'), data.get('end_date')
        if start and end and end < start:
            self.add_error('end_date', 'Выпуск не может быть раньше начала обучения.')
        students = data.get('students_count') or 0
        for field in ('wants_internship', 'expected_interns', 'actual_interns'):
            value = data.get(field) or 0
            if value > students:
                self.add_error(field, 'Не может быть больше, чем обучающихся в группе.')
        return data
