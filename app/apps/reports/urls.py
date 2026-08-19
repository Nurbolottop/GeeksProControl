from django.urls import path

from apps.reports import views

app_name = 'reports'

urlpatterns = [
    path('weekly/', views.weekly_list, name='weekly_list'),
    path('weekly/generate/', views.weekly_generate, name='weekly_generate'),
    path('weekly/<int:pk>/', views.weekly_detail, name='weekly_detail'),
    path('kpi/', views.kpi_view, name='kpi'),
]
