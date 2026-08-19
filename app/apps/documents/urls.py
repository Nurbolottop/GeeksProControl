from django.urls import path

from apps.documents import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='list'),
    path('create/', views.document_create, name='create'),
    path('<int:pk>/edit/', views.document_update, name='update'),
    path('<int:pk>/approve/', views.document_approve, name='approve'),
]
