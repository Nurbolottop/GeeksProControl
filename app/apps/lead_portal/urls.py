from django.urls import path

from apps.lead_portal import views

app_name = 'lead_portal'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('resume/', views.resume, name='resume'),
    path(
        'notifications/<int:pk>/close/', views.notification_close,
        name='notification_close',
    ),
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('<int:pk>/team/add/', views.member_add, name='member_add'),
    path(
        '<int:pk>/team/<int:member_pk>/edit/', views.member_edit,
        name='member_edit',
    ),
    path(
        '<int:pk>/team/<int:member_pk>/delete/', views.member_delete,
        name='member_delete',
    ),
    path('<int:pk>/attendance/create/', views.meeting_create, name='meeting_create'),
    path(
        '<int:pk>/attendance/<int:meeting_pk>/', views.meeting_detail,
        name='meeting_detail',
    ),
    path(
        '<int:pk>/attendance/<int:meeting_pk>/mark/', views.meeting_mark_toggle,
        name='meeting_mark_toggle',
    ),
    path(
        '<int:pk>/attendance/<int:meeting_pk>/mark-all/', views.meeting_mark_all,
        name='meeting_mark_all',
    ),
    path(
        '<int:pk>/attendance/<int:meeting_pk>/score/', views.meeting_score,
        name='meeting_score',
    ),
    path(
        '<int:pk>/interns/<int:intern_pk>/', views.intern_detail,
        name='intern_detail',
    ),
]
