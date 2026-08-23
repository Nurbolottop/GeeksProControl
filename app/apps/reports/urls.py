from django.urls import path

from apps.reports import views

app_name = 'reports'

urlpatterns = [
    path('weekly/', views.weekly_list, name='weekly_list'),
    path('weekly/generate/', views.weekly_generate, name='weekly_generate'),
    path('weekly/<int:pk>/', views.weekly_detail, name='weekly_detail'),
    path('weekly/<int:pk>/delete/', views.weekly_delete, name='weekly_delete'),
    path('written/', views.written_list, name='written_list'),
    path('written/<int:pk>/edit/', views.written_update, name='written_update'),
    path('written/<int:pk>/delete/', views.written_delete, name='written_delete'),
    path('kpi/', views.kpi_view, name='kpi'),
]
