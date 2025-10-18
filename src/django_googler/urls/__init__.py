"""
URL configurations for django_googler.

This module provides pre-configured URL patterns for easy integration.

Usage:
    # For regular Django views
    from django.urls import include, path

    urlpatterns = [
        path('auth/google/', include('django_googler.urls.default')),
    ]

    # For Django Rest Framework API views
    from django.urls import include, path

    urlpatterns = [
        path('api/auth/google/', include('django_googler.urls.api')),
    ]

    # Or use both
    urlpatterns = [
        path('auth/google/', include('django_googler.urls.default')),
        path('api/auth/google/', include('django_googler.urls.api')),
    ]
"""

from django_googler.urls.default import urlpatterns

__all__ = ["urlpatterns"]
