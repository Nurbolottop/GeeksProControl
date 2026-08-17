from django.urls import path

from apps.reports import views

app_name = 'reports'

urlpatterns = [
    path('weekly/', views.weekly_list, name='weekly_list'),
    path('weekly/generate/', views.weekly_generate, name='weekly_generate'),
    path('weekly/<int:pk>/', views.weekly_detail, name='weekly_detail'),
    path('monthly/', views.monthly_list, name='monthly_list'),
    path('monthly/generate/', views.monthly_generate, name='monthly_generate'),
    path('monthly/<int:pk>/', views.monthly_detail, name='monthly_detail'),
    path('kpi/', views.kpi_view, name='kpi'),
]
