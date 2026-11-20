"""
URL configurations for django_googler.

This module provides pre-configured URL patterns for easy integration.

Usage::

    # For regular Django session views:
    #   GET /auth/google/login/
    #   GET /auth/google/callback/
    from django.urls import include, path

    urlpatterns = [
        path("auth/", include("django_googler.urls.default")),
    ]

    # For Django REST Framework API views:
    #   GET  /api/auth/google/login/
    #   POST /api/auth/google/callback/
    #   POST /api/auth/google/refresh/
    #   POST /api/auth/google/logout/
    #   GET  /api/auth/me/
    urlpatterns = [
        path("api/auth/", include("django_googler.urls.api")),
    ]

    # Or use both:
    urlpatterns = [
        path("auth/", include("django_googler.urls.default")),
        path("api/auth/", include("django_googler.urls.api")),
    ]
"""

from django_googler.urls.default import urlpatterns

__all__ = ["urlpatterns"]
