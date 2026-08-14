from django.urls import path

from apps.interns import views

app_name = 'interns'

urlpatterns = [
    path('', views.intern_list, name='list'),
    path('create/', views.intern_create, name='create'),
    path('<int:pk>/', views.intern_detail, name='detail'),
    path('<int:pk>/edit/', views.intern_update, name='update'),
    path('<int:pk>/evaluate/', views.evaluation_add, name='evaluate'),
]
