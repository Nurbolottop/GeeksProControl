from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.interns.views import (
    profile_apply, resume_bank_apply, talent_reserve_apply,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('resume-bank/', resume_bank_apply, name='resume_bank_apply'),
    path('intern-profile/', profile_apply, name='intern_profile_apply'),
    path('talent-reserve/', talent_reserve_apply, name='talent_reserve_apply'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.dashboard.urls')),
    path('flows/', include('apps.flows.urls')),
    path('attendance/', include('apps.attendance.urls')),
    path('project-daily/', include('apps.dailycheck.urls')),
    path('projects/', include('apps.projects.urls')),
    path('clients/', include('apps.clients.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('teams/', include('apps.teams.urls')),
    path('interns/', include('apps.interns.urls')),
    path('documents/', include('apps.documents.urls')),
    path('meetings/', include('apps.meetings.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('risks/', include('apps.risks.urls')),
    path('resources/', include('apps.resources.urls')),
    path('reports/', include('apps.reports.urls')),
    path('pm/', include('apps.pm_portal.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
