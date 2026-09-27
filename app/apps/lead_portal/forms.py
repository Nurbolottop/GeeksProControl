from django import forms


class LeadToReserveForm(forms.Form):
    """Что тимлид добавляет к карточке кандидата, отправляя его в резерв.

    Навыки просим обязательно: без них карточка в резерве пустая, а
    тимлид знает человека по работе лучше всех.
    """

    skills = forms.CharField(
        label='Навыки и технологии',
        help_text='Через запятую: языки, фреймворки, инструменты.',
        widget=forms.Textarea(attrs={
            'rows': 3, 'placeholder': 'Python, Django, PostgreSQL, Docker',
        }),
    )
    comment = forms.CharField(
        label='Комментарий тимлида', required=False,
        help_text='Как он(а) работает в команде — видят только сотрудники.',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
