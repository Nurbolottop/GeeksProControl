from django.urls import path

from apps.flows import views

app_name = 'flows'

urlpatterns = [
    path('', views.flow_list, name='list'),
    path('create/', views.flow_create, name='create'),
    path('<int:pk>/', views.flow_detail, name='detail'),
    path('<int:pk>/edit/', views.flow_update, name='update'),
]
