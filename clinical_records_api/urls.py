"""
URL configuration for clinical_records_api project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.urls import path, include
from django.contrib.auth import views as auth_views
from clinical_records.views import dashboard_views, auth_views as clinical_auth_views, sso_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include('clinical_records.urls')),
    
    # SSO endpoints for RxBackend integration
    path("sso/login/", sso_views.sso_login, name='sso_login'),
    path("sso/logout/", sso_views.sso_logout, name='sso_logout'),
    path("sso/status/", sso_views.sso_status, name='sso_status'),
    
    # Regular authentication
    path("login/", auth_views.LoginView.as_view(template_name='clinical_records/login.html'), name='login'),
    path("logout/", clinical_auth_views.logout_view, name='logout'),
    path("dashboard/", dashboard_views.dashboard_home, name='dashboard'),
    path("records/", dashboard_views.records_list_page, name='records_list'),
    path("", dashboard_views.landing_page, name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
