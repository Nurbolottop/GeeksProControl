from django.contrib import admin

from apps.training.models import Specialization, TrainingGroup


@admin.register(Specialization)
class SpecializationAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(TrainingGroup)
class TrainingGroupAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'specialization', 'branch', 'end_date',
        'students_count', 'expected_interns', 'actual_interns',
    )
    list_filter = ('specialization', 'branch')
