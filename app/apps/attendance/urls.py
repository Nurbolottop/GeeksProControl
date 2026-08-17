from django.urls import path

from apps.attendance import views

app_name = 'attendance'

urlpatterns = [
    path('groups/<int:pk>/', views.group_sheet, name='group_sheet'),
    path('groups/<int:pk>/meetings/create/', views.meeting_create,
         name='meeting_create'),
    path('meetings/<int:pk>/delete/', views.meeting_delete, name='meeting_delete'),
    path('meetings/<int:pk>/toggle/', views.toggle, name='toggle'),
    path('meetings/<int:pk>/mark-all/', views.meeting_mark_all, name='mark_all'),
]
