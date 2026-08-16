from django.urls import path

from apps.attendance import views

app_name = 'attendance'

urlpatterns = [
    path('groups/<int:pk>/', views.group_sheet, name='group_sheet'),
    path('groups/<int:pk>/toggle/', views.toggle, name='toggle'),
    path('groups/<int:pk>/mark-day/', views.mark_day, name='mark_day'),
]
