import os

from django import forms
from django.conf import settings

from apps.documents.models import Document


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            'project', 'doc_type', 'number', 'file', 'document_date',
            'status', 'is_signed', 'signed_date', 'comment',
        ]
        widgets = {
            'document_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'signed_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'comment': forms.Textarea(attrs={'rows': 2}),
        }

    def clean_file(self):
        """Проверка расширения и размера файла (ТЗ §35)."""
        file = self.cleaned_data.get('file')
        if not file or not hasattr(file, 'size'):
            return file
        extension = os.path.splitext(file.name)[1].lstrip('.').lower()
        allowed = settings.ALLOWED_UPLOAD_EXTENSIONS
        if extension not in allowed:
            raise forms.ValidationError(
                f'Файлы .{extension} запрещены. Разрешены: {", ".join(allowed)}.',
            )
        if file.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
            raise forms.ValidationError('Файл больше 20 МБ.')
        return file

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_signed') and not cleaned.get('signed_date'):
            self.add_error('signed_date', 'Укажите дату подписания.')
        return cleaned
