from django.urls import path

from apps.projects import views

app_name = 'projects'

urlpatterns = [
    path('', views.project_list, name='list'),
    path('in-progress/', views.project_list,
         {'category': 'in_progress'}, name='list_in_progress'),
    path('rejected/', views.project_list,
         {'category': 'rejected'}, name='list_rejected'),
    path('completed/', views.project_list,
         {'category': 'completed'}, name='list_completed'),
    path('kanban/', views.project_kanban, name='kanban'),
    path('create/', views.project_create, name='create'),
    path('<int:pk>/', views.project_detail, name='detail'),
    path('<int:pk>/edit/', views.project_update, name='update'),
    path('<int:pk>/move-stage/', views.project_move_stage, name='move_stage'),
    path('<int:pk>/complete/', views.project_complete, name='complete'),
    path('stages/<int:pk>/', views.stage_update, name='stage_update'),
    path('stages/<int:pk>/row/', views.stage_row, name='stage_row'),
    path('stages/<int:pk>/complete/', views.stage_complete, name='stage_complete'),
    path('stages/<int:pk>/extend/', views.stage_extend, name='stage_extend'),
    path('<int:pk>/section/<str:section>/', views.project_section, name='section'),
    path('<int:pk>/access/add/', views.access_create, name='access_create'),
    path('access/<int:pk>/edit/', views.access_update, name='access_update'),
    path('access/<int:pk>/delete/', views.access_delete, name='access_delete'),
]
