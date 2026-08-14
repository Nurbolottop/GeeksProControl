from django.contrib import admin

from apps.meetings.models import Meeting, MeetingDecision


class MeetingDecisionInline(admin.TabularInline):
    model = MeetingDecision
    extra = 0


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ('topic', 'date', 'time', 'meeting_type', 'project')
    list_filter = ('meeting_type',)
    search_fields = ('topic',)
    inlines = [MeetingDecisionInline]
