from django.urls import path

from apps.documents import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='list'),
    path('create/', views.document_create, name='create'),
    path('<int:pk>/edit/', views.document_update, name='update'),
    path('<int:pk>/approve/', views.document_approve, name='approve'),
    path('templates/', views.template_list, name='templates'),
    path('templates/create/', views.template_create, name='template_create'),
    path(
        'templates/<int:pk>/edit/', views.template_update,
        name='template_update',
    ),
    path(
        'templates/<int:pk>/delete/', views.template_delete,
        name='template_delete',
    ),
    path(
        'brief-link/<int:project_pk>/create/', views.brief_link_create,
        name='brief_link_create',
    ),
]
