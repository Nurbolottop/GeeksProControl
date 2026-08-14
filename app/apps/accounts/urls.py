from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path

from apps.accounts.views import dev_login

urlpatterns = [
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='accounts/login.html',
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

if settings.DEBUG:
    urlpatterns += [path('dev-login/', dev_login, name='dev_login')]
