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
]
