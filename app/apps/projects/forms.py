from django import forms

from apps.projects.models import Project, ProjectAccess, ProjectStage


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
            'head_comment',
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


class ProjectCreateForm(forms.ModelForm):
    """Новый проект: только то, что известно, когда проект берут в работу.

    Ссылки, домен, staging, прод, сроки и прогресс появляются позже —
    они заполняются поблочно в «Обзоре».
    """

    class Meta:
        model = Project
        fields = ['name', 'client', 'city', 'project_type', 'description']
        widgets = {
            'name': forms.TextInput(
                attrs={'placeholder': 'Например: Омур', 'autofocus': True},
            ),
            'city': forms.TextInput(attrs={'placeholder': 'Бишкек или Ош'}),
            'description': forms.Textarea(
                attrs={'rows': 3, 'placeholder': 'Что делаем и для кого'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].required = False
        self.fields['client'].empty_label = 'Выберите заказчика'


class ProjectProgressForm(forms.ModelForm):
    """Инлайн-форма: прогресс и текущий этап."""

    class Meta:
        model = Project
        fields = ['progress', 'current_stage']


class ProjectClientForm(forms.ModelForm):
    """Инлайн-форма: заказчик, город и контакты клиента.

    Контактные поля принадлежат клиенту, поэтому сохраняются отдельно.
    """

    contact_name = forms.CharField(
        label='Контактное лицо', required=False, max_length=255,
    )
    phone = forms.CharField(label='Телефон', required=False, max_length=32)
    email = forms.EmailField(label='Email', required=False)

    class Meta:
        model = Project
        fields = ['client', 'city']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        client = self.instance.client
        if client:
            self.fields['contact_name'].initial = client.contact_name
            self.fields['phone'].initial = client.phone
            self.fields['email'].initial = client.email

    def save_client(self):
        """Сохраняет контакты в карточку клиента (вызывается после проекта)."""
        client = self.instance.client
        if not client:
            return
        client.contact_name = self.cleaned_data['contact_name']
        client.phone = self.cleaned_data['phone']
        client.email = self.cleaned_data['email']
        client.save(update_fields=[
            'contact_name', 'phone', 'email', 'updated_at',
        ])


class ProjectAboutForm(forms.ModelForm):
    """Инлайн-форма: описание проекта и комментарий руководителя."""

    class Meta:
        model = Project
        fields = ['description', 'head_comment']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'head_comment': forms.Textarea(attrs={'rows': 2}),
        }


class ProjectLinksForm(forms.ModelForm):
    """Инлайн-форма: ссылки проекта."""

    class Meta:
        model = Project
        fields = [
            'staging_url', 'production_url', 'github_url', 'figma_url', 'domain',
        ]
        widgets = {
            # autocomplete=off — иначе браузер подставляет адрес текущей страницы
            'staging_url': forms.URLInput(attrs={'autocomplete': 'off'}),
            'production_url': forms.URLInput(attrs={'autocomplete': 'off'}),
            'github_url': forms.URLInput(attrs={'autocomplete': 'off'}),
            'figma_url': forms.URLInput(attrs={'autocomplete': 'off'}),
            'domain': forms.TextInput(attrs={'autocomplete': 'off'}),
        }


class ProjectDetailsForm(forms.ModelForm):
    """Инлайн-форма: статус, этап, поток, приоритет, тип.

    ПМ и тимлиды здесь не редактируются — они назначаются в команде
    проекта, чтобы человек был один и в табеле, и в карточке.
    """

    class Meta:
        model = Project
        fields = [
            'status', 'current_stage', 'flow', 'priority', 'project_type',
        ]


class ProjectDatesForm(forms.ModelForm):
    """Инлайн-форма: сроки. Перенос deadline требует причину (ТЗ §21)."""

    change_reason = forms.CharField(
        label='Причина переноса срока', required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Например: клиент задержал материалы'}),
    )

    class Meta:
        model = Project
        fields = [
            'contract_date', 'start_date', 'planned_end_date', 'actual_end_date',
        ]
        widgets = {
            'contract_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'start_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'planned_end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'actual_end_date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def clean(self):
        cleaned = super().clean()
        if 'planned_end_date' in self.changed_data:
            old_value = Project.objects.get(pk=self.instance.pk).planned_end_date
            if old_value and not cleaned.get('change_reason', '').strip():
                self.add_error(
                    'change_reason',
                    'При переносе срока обязательно укажите причину.',
                )
        return cleaned


class ProjectAccessForm(forms.ModelForm):
    class Meta:
        model = ProjectAccess
        fields = ['service', 'url', 'login', 'password', 'comment']
        widgets = {
            'service': forms.TextInput(
                attrs={'placeholder': 'Админка сайта / Хостинг / База данных…'},
            ),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }


class StageUpdateForm(forms.ModelForm):
    """Настройка этапа: статус, дедлайн и комментарий."""

    class Meta:
        model = ProjectStage
        fields = ['status', 'deadline', 'comment']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'comment': forms.TextInput(),
        }


class StageExtendForm(forms.Form):
    """Продление дедлайна этапа — новая дата и обязательная причина."""

    deadline = forms.DateField(
        label='Новый deadline',
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    reason = forms.CharField(
        label='Причина продления',
        widget=forms.TextInput(
            attrs={'placeholder': 'Например: клиент задержал материалы'},
        ),
    )
