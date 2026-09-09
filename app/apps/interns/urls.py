from django.urls import path

from apps.interns import views

app_name = 'interns'

urlpatterns = [
    path('', views.intern_list, name='list'),
    path('create/', views.intern_create, name='create'),
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
]
