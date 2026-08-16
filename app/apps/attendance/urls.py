from django.urls import path

from apps.attendance import views

app_name = 'attendance'

urlpatterns = [
    path('groups/<int:pk>/', views.group_sheet, name='group_sheet'),
    path('groups/<int:pk>/plan/', views.plan_list, name='plan_list'),
    path('groups/<int:pk>/generate/', views.generate, name='generate'),
    path('plans/<int:pk>/delete/', views.plan_delete, name='plan_delete'),
    path('meetings/<int:pk>/toggle/', views.toggle, name='toggle'),
    path('meetings/<int:pk>/mark-all/', views.meeting_mark_all, name='mark_all'),
]
