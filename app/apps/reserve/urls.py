from django.urls import path

from apps.reserve import views

app_name = 'reserve'

urlpatterns = [
    path('', views.candidate_list, name='list'),
    path('create/', views.candidate_create, name='create'),
    path('from-intern/', views.candidate_from_intern, name='from_intern'),
    path('invite/', views.invite_create, name='invite_create'),
    path('invite/<int:pk>/disable/', views.invite_disable, name='invite_disable'),
    path('<int:pk>/', views.candidate_detail, name='detail'),
    path('<int:pk>/edit/', views.candidate_update, name='update'),
    path('<int:pk>/evaluate/', views.candidate_evaluate, name='evaluate'),
    path('<int:pk>/status/', views.candidate_status, name='status'),
    path('<int:pk>/invite/', views.invite_create, name='invite'),
    path('<int:pk>/recommend/', views.recommendation_create, name='recommend'),
    path(
        'recommendation/<int:pk>/status/', views.recommendation_status,
        name='recommendation_status',
    ),
]
