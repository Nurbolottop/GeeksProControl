from django.urls import path

from apps.dashboard import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
]
