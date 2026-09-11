from django.urls import path

from apps.interns import views

app_name = 'interns'

urlpatterns = [
    path('', views.intern_list, name='list'),
    path('create/', views.intern_create, name='create'),
    path('by-project/', views.by_project, name='by_project'),
    path(
        'profile-link/new/', views.profile_link_create,
        name='profile_link_create',
    ),
    path(
        'profile-link/disable/', views.profile_link_disable,
        name='profile_link_disable',
    ),
    path(
        'profile-link/answers/', views.profile_link_answers,
        name='profile_link_answers',
    ),
    path('reserve/', views.reserve_list, name='reserve'),
    path('reserve/add/', views.reserve_create, name='reserve_create'),
    path('reserve/<int:pk>/edit/', views.reserve_update, name='reserve_update'),
    path('reserve/<int:pk>/delete/', views.reserve_delete, name='reserve_delete'),
    path(
        'reserve/<int:pk>/priority/', views.reserve_set_priority,
        name='reserve_set_priority',
    ),
    path('resume-bank/', views.resume_bank_list, name='resume_bank'),
    path('graduates/', views.graduates_list, name='graduates'),
    path('<int:pk>/', views.intern_detail, name='detail'),
    path('<int:pk>/edit/', views.intern_update, name='update'),
    path('<int:pk>/evaluate/', views.evaluation_add, name='evaluate'),
    path('<int:pk>/delete/', views.intern_delete, name='delete'),
    path('<int:pk>/grant-access/', views.grant_pm_access, name='grant_access'),
    path('<int:pk>/project/add/', views.intern_project_add, name='project_add'),
    path(
        '<int:pk>/project/<int:member_pk>/remove/', views.intern_project_remove,
        name='project_remove',
    ),
]
