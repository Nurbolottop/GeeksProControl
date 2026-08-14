from django.urls import path

from apps.meetings import views

app_name = 'meetings'

urlpatterns = [
    path('', views.meeting_list, name='list'),
    path('create/', views.meeting_create, name='create'),
    path('<int:pk>/', views.meeting_detail, name='detail'),
    path('<int:pk>/edit/', views.meeting_update, name='update'),
    path('decisions/<int:pk>/create-task/', views.decision_create_task, name='decision_task'),
]
