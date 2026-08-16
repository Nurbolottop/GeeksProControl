from django.contrib import admin

from apps.attendance.models import Attendance, GroupMeeting, MeetingPlan


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0


@admin.register(MeetingPlan)
class MeetingPlanAdmin(admin.ModelAdmin):
    list_display = ('group', 'kind', 'times_per_week', 'host', 'is_active')
    list_filter = ('kind', 'is_active')


@admin.register(GroupMeeting)
class GroupMeetingAdmin(admin.ModelAdmin):
    list_display = ('date', 'group', 'kind', 'status', 'host')
    list_filter = ('kind', 'status', 'group__flow')
    date_hierarchy = 'date'
    inlines = [AttendanceInline]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('meeting', 'intern', 'status', 'marked_by')
    list_filter = ('status', 'meeting__kind')
    search_fields = ('intern__full_name',)
