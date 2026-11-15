"""
URL configuration for doday project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from doday.ratelimit import rate_limit
from events import views as events_views
from events.forms import EmailAuthenticationForm

urlpatterns = [
    path('admin/', admin.site.urls),
    # REQ-29: set_language view used by the EN/ES switcher in the header.
    path('i18n/', include('django.conf.urls.i18n')),
    path('accounts/signup/', events_views.signup, name='signup'),
    path(
        'accounts/login/',
        # 10 attempts per IP every 5 minutes: slows down password guessing.
        rate_limit('login', limit=10, window=300)(
            auth_views.LoginView.as_view(authentication_form=EmailAuthenticationForm)
        ),
        name='login',
    ),
    # Password reset with the project's own templates. They are declared here,
    # before the include below, because django.contrib.admin ships templates
    # with the default names and would otherwise win.
    path(
        'accounts/password_reset/',
        # 5 requests per IP per hour: nobody can use the form to flood an inbox.
        rate_limit('password_reset', limit=5, window=3600)(
            auth_views.PasswordResetView.as_view(
                template_name='accounts/password_reset_form.html',
                email_template_name='accounts/password_reset_email.txt',
                subject_template_name='accounts/password_reset_subject.txt',
            )
        ),
        name='password_reset',
    ),
    path(
        'accounts/password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'),
        name='password_reset_done',
    ),
    path(
        'accounts/reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'),
        name='password_reset_confirm',
    ),
    path(
        'accounts/reset/done/',
        auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'),
        name='password_reset_complete',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('analytics/', include('analytics.urls')),
    path('', include('navigation.urls')),
    path('', include('events.urls')),
]
