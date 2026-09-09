from django.contrib import admin

from apps.interns.models import (
    Intern, InternEvaluation, ProfileFormLink, TalentReserveCandidate,
)


class InternEvaluationInline(admin.TabularInline):
    model = InternEvaluation
    extra = 0


@admin.register(Intern)
class InternAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'specialization', 'status', 'training_group',
        'team_lead', 'rating', 'is_archived',
    )
    list_filter = ('specialization', 'status', 'branch', 'is_archived')
    search_fields = ('full_name', 'phone', 'email')
    inlines = [InternEvaluationInline]


@admin.register(TalentReserveCandidate)
class TalentReserveCandidateAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'specialization', 'desired_role', 'city',
        'priority', 'is_archived',
    )
    list_filter = ('specialization', 'city', 'is_archived')
    search_fields = ('full_name', 'phone', 'email')
    ordering = ('-priority', '-created_at')


@admin.register(ProfileFormLink)
class ProfileFormLinkAdmin(admin.ModelAdmin):
    list_display = ('token', 'is_active', 'submissions', 'created_by', 'created_at')
    list_filter = ('is_active',)
    readonly_fields = ('token', 'submissions', 'created_at', 'updated_at')
