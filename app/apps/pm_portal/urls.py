from django.urls import path

from apps.pm_portal import views

app_name = 'pm_portal'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('<int:pk>/report/', views.report_create, name='report_create'),
    path(
        '<int:pk>/report/<int:report_pk>/edit/', views.report_update,
        name='report_update',
    ),
    path(
        '<int:pk>/report/<int:report_pk>/delete/', views.report_delete,
        name='report_delete',
    ),
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
        '<int:pk>/interns/<int:intern_pk>/evaluate/', views.evaluation_add,
        name='evaluation_add',
    ),
]
