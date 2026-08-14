from django.urls import path

from apps.resources import views

app_name = 'resources'

urlpatterns = [
    path('forecast/', views.forecast, name='forecast'),
    path('graduations/', views.graduations, name='graduations'),
    path('planned/create/', views.planned_create, name='planned_create'),
    path('planned/<int:pk>/', views.planned_update, name='planned_update'),
]
