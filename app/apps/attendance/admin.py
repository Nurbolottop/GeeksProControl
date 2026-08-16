from django.contrib import admin

from apps.attendance.models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('date', 'group', 'intern', 'status', 'marked_by')
    list_filter = ('status', 'date', 'group__flow')
    search_fields = ('intern__full_name',)
    date_hierarchy = 'date'
