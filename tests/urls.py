"""
URL configuration for django-googler tests.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("auth/", include("django_googler.urls.default")),
    path("api/auth/", include("django_googler.urls.api")),
]
