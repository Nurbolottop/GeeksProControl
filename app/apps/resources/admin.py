from django.contrib import admin

from apps.resources.models import PlannedProject, PlannedProjectNeed


class PlannedProjectNeedInline(admin.TabularInline):
    model = PlannedProjectNeed
    extra = 0


@admin.register(PlannedProject)
class PlannedProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'status', 'probability', 'expected_start', 'duration_months',
    )
    list_filter = ('status',)
    inlines = [PlannedProjectNeedInline]
