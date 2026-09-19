from django.urls import path

from apps.pm_portal import views

app_name = 'pm_portal'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('<int:pk>/', views.project_detail, name='project_detail'),
    path('<int:pk>/stages/<int:stage_pk>/', views.stage_set, name='stage_set'),
    path('<int:pk>/stages/confirm/', views.stages_confirm, name='stages_confirm'),
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
    path(
        '<int:pk>/attendance/<int:meeting_pk>/', views.meeting_detail,
        name='meeting_detail',
    ),
    path(
        '<int:pk>/interns/<int:intern_pk>/', views.intern_detail,
        name='intern_detail',
    ),
    path('<int:pk>/documents/upload/', views.document_upload, name='document_upload'),
    path(
        '<int:pk>/documents/<int:document_pk>/edit/', views.document_update,
        name='document_update',
    ),
    path(
        '<int:pk>/documents/<int:document_pk>/approve/', views.document_approve,
        name='document_approve',
    ),
    path(
        '<int:pk>/documents/brief-link/', views.brief_link_create,
        name='brief_link_create',
    ),
    path('<int:pk>/client/', views.client_edit, name='client_edit'),
    path('<int:pk>/edit/<str:section>/', views.project_edit, name='project_edit'),
]
