from django import forms

from apps.meetings.models import Meeting, MeetingDecision


class MeetingForm(forms.ModelForm):
    class Meta:
        model = Meeting
        fields = [
            'topic', 'date', 'time', 'meeting_type', 'project',
            'participants', 'external_participants', 'agenda',
            'discussion', 'next_meeting_date',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'time': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'next_meeting_date': forms.DateInput(
                attrs={'type': 'date'}, format='%Y-%m-%d',
            ),
            'agenda': forms.Textarea(attrs={'rows': 5}),
            'discussion': forms.Textarea(attrs={'rows': 5}),
        }


class MeetingDecisionForm(forms.ModelForm):
    class Meta:
        model = MeetingDecision
        fields = ['text', 'responsible', 'deadline', 'status']
        widgets = {
            'text': forms.Textarea(attrs={'rows': 2}),
            'deadline': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }
