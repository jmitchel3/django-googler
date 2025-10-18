"""
Django app configuration for django_googler.
"""

from django.apps import AppConfig


class DjangoGooglerConfig(AppConfig):
    """Configuration for django_googler app."""

    name = "django_googler"
    verbose_name = "Django Googler"

    def ready(self):
        """Import checks when app is ready."""
        from django_googler import checks  # noqa: F401
