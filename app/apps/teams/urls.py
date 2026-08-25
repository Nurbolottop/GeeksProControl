from django.urls import path

from apps.teams import views

app_name = 'teams'

urlpatterns = [
    path('', views.team_overview, name='overview'),
    path('project/<int:project_pk>/add/', views.member_add, name='member_add'),
    path('group/<int:group_pk>/add/', views.member_add_to_group,
         name='member_add_group'),
    path('member/<int:pk>/edit/', views.member_edit, name='member_edit'),
    path('member/<int:pk>/delete/', views.member_delete, name='member_delete'),
    path('project/<int:project_pk>/clear/', views.team_clear, name='team_clear'),
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/add/', views.lead_add, name='lead_add'),
    path('leads/<int:pk>/remove/', views.lead_remove, name='lead_remove'),
    path('pm/', views.pm_list, name='pm_list'),
    path('pm/add/', views.pm_add, name='pm_add'),
    path('pm/<int:pk>/remove/', views.pm_remove, name='pm_remove'),
]
