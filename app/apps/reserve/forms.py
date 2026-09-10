from django import forms

from apps.clients.models import Client
from apps.reserve.models import (
    CandidateStatus, ReserveCandidate, ReserveRecommendation,
)

DATE = forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')

# Что кандидат заполняет о себе сам — один список на анкету и на
# внутреннюю форму, чтобы поля не разъезжались.
PUBLIC_FIELDS = [
    'full_name', 'birth_date', 'city', 'phone', 'telegram', 'email', 'photo',
    'specialization', 'direction_other', 'desired_position', 'expected_level',
    'skills', 'work_experience', 'internship_experience', 'education',
    'courses', 'english_level', 'other_languages', 'about',
    'resume_file', 'resume_url', 'github_url', 'linkedin_url',
    'portfolio_url', 'behance_url', 'website_url', 'project_links',
    'is_looking_for_job', 'work_format', 'employment_type',
    'ready_for_internship', 'ready_to_relocate', 'available_from',
    'desired_salary', 'target_positions',
]

TEXT_WIDGETS = {
    'skills': forms.Textarea(attrs={'rows': 2}),
    'work_experience': forms.Textarea(attrs={'rows': 3}),
    'internship_experience': forms.Textarea(attrs={'rows': 2}),
    'education': forms.Textarea(attrs={'rows': 2}),
    'courses': forms.Textarea(attrs={'rows': 2}),
    'about': forms.Textarea(attrs={'rows': 3}),
    'project_links': forms.Textarea(attrs={'rows': 2}),
    'target_positions': forms.Textarea(attrs={'rows': 2}),
    'birth_date': DATE,
    'available_from': DATE,
}


class ReserveApplyForm(forms.ModelForm):
    """Публичная анкета кандидата — заполняется по персональной ссылке.

    Внутренних данных (оценки, статусы, комментарии сотрудников) здесь
    нет и быть не может: форма знает только про поля самого кандидата.
    """

    consent_given = forms.BooleanField(
        required=True,
        label=(
            'Я согласен на обработку моих данных и передачу моего резюме и '
            'профессиональной информации потенциальным работодателям'
        ),
        error_messages={'required': 'Без согласия отправить анкету нельзя.'},
    )

    class Meta:
        model = ReserveCandidate
        fields = PUBLIC_FIELDS + ['consent_given']
        widgets = TEXT_WIDGETS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['phone'].required = True
        self.fields['specialization'].empty_label = 'Другое / не из списка'


class ReserveCandidateForm(forms.ModelForm):
    """Карточка кандидата глазами сотрудника: анкетные поля + учебная часть."""

    class Meta:
        model = ReserveCandidate
        fields = PUBLIC_FIELDS + [
            'intern', 'training_group', 'study_specialization', 'teacher',
            'curator', 'study_start', 'study_end', 'status',
        ]
        widgets = dict(TEXT_WIDGETS, **{
            'study_start': DATE,
            'study_end': DATE,
        })

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['full_name'].required = True
        self.fields['specialization'].empty_label = 'Другое / не из списка'
        self.fields['intern'].empty_label = 'Не привязан к стажёру'
        self.fields['intern'].help_text = (
            'Проекты, роли и периоды подтянутся из команд этого стажёра.'
        )


class ReserveEvaluationForm(forms.ModelForm):
    """Внутренняя оценка — кандидат её не видит и не заполняет."""

    class Meta:
        model = ReserveCandidate
        fields = [field for field, _ in ReserveCandidate.EVALUATION_CRITERIA] + [
            'geekspro_level', 'recommended_position', 'strengths', 'improvements',
            'comment_teacher', 'comment_pm', 'comment_lead', 'comment_curator',
            'decision', 'decision_comment',
        ]
        widgets = {
            'strengths': forms.Textarea(attrs={'rows': 2}),
            'improvements': forms.Textarea(attrs={'rows': 2}),
            'comment_teacher': forms.Textarea(attrs={'rows': 2}),
            'comment_pm': forms.Textarea(attrs={'rows': 2}),
            'comment_lead': forms.Textarea(attrs={'rows': 2}),
            'comment_curator': forms.Textarea(attrs={'rows': 2}),
            'decision_comment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field, _ in ReserveCandidate.EVALUATION_CRITERIA:
            self.fields[field].widget = forms.NumberInput(
                attrs={'min': 1, 'max': 10, 'step': 1, 'placeholder': '1–10'},
            )


class ReserveRecommendationForm(forms.ModelForm):
    """Рекомендация кандидата компании."""

    class Meta:
        model = ReserveRecommendation
        fields = ['company', 'company_name', 'vacancy', 'sent_on', 'status', 'comment']
        widgets = {
            'sent_on': DATE,
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['company'].queryset = Client.objects.active().order_by('organization')
        self.fields['company'].empty_label = 'Компания вне базы заказчиков'
        if not self.initial.get('sent_on'):
            from django.utils import timezone

            self.initial['sent_on'] = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('company') and not cleaned.get('company_name'):
            raise forms.ValidationError(
                'Выберите компанию из базы или впишите название.',
            )
        return cleaned


class StatusChangeForm(forms.Form):
    """Смена статуса кандидата с обязательным следом в истории."""

    status = forms.ChoiceField(choices=CandidateStatus.choices, label='Новый статус')
    comment = forms.CharField(
        label='Комментарий', required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )


class InviteForm(forms.Form):
    """Персональная ссылка на анкету."""

    TTL_CHOICES = [
        ('7', '7 дней'), ('3', '3 дня'), ('14', '14 дней'),
        ('30', '30 дней'), ('', 'Без срока'),
    ]

    recipient = forms.CharField(
        label='Кому отправляем', max_length=255, required=False,
        help_text='ФИО или контакт — чтобы помнить, кому ушла ссылка.',
    )
    ttl_days = forms.ChoiceField(
        label='Срок действия', choices=TTL_CHOICES, required=False, initial='7',
    )

    def ttl(self) -> int | None:
        raw = self.cleaned_data.get('ttl_days') or ''
        return int(raw) if raw.isdigit() else None
