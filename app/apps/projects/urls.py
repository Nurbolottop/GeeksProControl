from django.urls import path

from apps.projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.project_list, name='list'),
    path('kanban/', views.project_kanban, name='kanban'),
    path('create/', views.project_create, name='create'),
    path('<int:pk>/', views.project_detail, name='detail'),
    path('<int:pk>/edit/', views.project_update, name='update'),
    path('<int:pk>/move-stage/', views.project_move_stage, name='move_stage'),
    path('<int:pk>/complete/', views.project_complete, name='complete'),
    path('stages/<int:pk>/', views.stage_update, name='stage_update'),
]
