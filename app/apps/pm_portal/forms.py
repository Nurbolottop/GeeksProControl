from apps.interns.forms import InternEvaluationForm
from apps.projects.models import Project


class PMInternEvaluationForm(InternEvaluationForm):
    """Та же форма оценки, но проект зафиксирован — ПМ не может подставить
    чужой проект вместо своего."""

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = Project.objects.filter(pk=project.pk)
        self.fields['project'].initial = project
        self.fields['project'].disabled = True
