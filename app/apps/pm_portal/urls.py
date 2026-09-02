from django.urls import path

from apps.pm_portal import views

app_name = 'pm_portal'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('<int:pk>/', views.project_detail, name='project_detail'),
]
