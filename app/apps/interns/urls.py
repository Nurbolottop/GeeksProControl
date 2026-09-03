from django.urls import path

from apps.interns import views

app_name = 'interns'

urlpatterns = [
    path('', views.intern_list, name='list'),
    path('create/', views.intern_create, name='create'),
    path('reserve/', views.reserve_list, name='reserve'),
    path('resume-bank/', views.resume_bank_list, name='resume_bank'),
    path('<int:pk>/', views.intern_detail, name='detail'),
    path('<int:pk>/edit/', views.intern_update, name='update'),
    path('<int:pk>/evaluate/', views.evaluation_add, name='evaluate'),
    path('<int:pk>/delete/', views.intern_delete, name='delete'),
    path('<int:pk>/grant-access/', views.grant_pm_access, name='grant_access'),
    path('<int:pk>/toggle-reserve/', views.toggle_reserve, name='toggle_reserve'),
]
