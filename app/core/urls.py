from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.reserve.views import apply_form as reserve_apply, share_profile as reserve_share
from apps.interns.views import (
    profile_apply, profile_link_expired, resume_bank_apply,
    talent_reserve_apply,
)
from apps.documents.views import brief_apply

urlpatterns = [
    path('admin/', admin.site.urls),
    path('resume-bank/', resume_bank_apply, name='resume_bank_apply'),
    # Постоянного адреса у анкеты нет: она живёт по сменяемому токену,
    # старый /intern-profile/ отвечает страницей «ссылка устарела».
    path('intern-profile/', profile_link_expired, name='intern_profile_expired'),
    path(
        'intern-profile/<str:token>/', profile_apply,
        name='intern_profile_apply',
    ),
    path('talent-reserve/', talent_reserve_apply, name='talent_reserve_apply'),
    # Анкета кандидата в резерв — только по персональной ссылке,
    # доступа к платформе она не даёт.
    path('reserve-profile/<str:token>/', reserve_apply, name='reserve_apply'),
    # Профиль кандидата для работодателя — тоже только по ссылке:
    # витрина без внутренних комментариев и истории.
    path('candidate/<str:token>/', reserve_share, name='reserve_share'),
    # Бриф проекта — ссылка выпускается под конкретный проект, заказчик
    # заполняет без входа, ответы попадают в Документы этого проекта.
    path('brief/<str:token>/', brief_apply, name='project_brief_apply'),
    path('', include('apps.accounts.urls')),
    path('', include('apps.dashboard.urls')),
    path('flows/', include('apps.flows.urls')),
    path('attendance/', include('apps.attendance.urls')),
    path('projects/', include('apps.projects.urls')),
    path('clients/', include('apps.clients.urls')),
    path('tasks/', include('apps.tasks.urls')),
    path('teams/', include('apps.teams.urls')),
    path('interns/', include('apps.interns.urls')),
    path('reserve/', include('apps.reserve.urls')),
    path('documents/', include('apps.documents.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('risks/', include('apps.risks.urls')),
    path('resources/', include('apps.resources.urls')),
    path('reports/', include('apps.reports.urls')),
    path('pm/', include('apps.pm_portal.urls')),
    path('lead/', include('apps.lead_portal.urls')),
    path('academy/', include('apps.training.urls')),
    path('scripts/', include('apps.scripts.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
