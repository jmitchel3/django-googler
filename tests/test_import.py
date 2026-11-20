"""
Tests for package imports, lazy exports, and URL modules.
"""

import pytest


def test_import_django_googler():
    """Test that django_googler can be imported and exposes __version__."""
    import django_googler

    assert hasattr(django_googler, "__version__")
    assert isinstance(django_googler.__version__, str)


def test_django_setup():
    """Test that Django is configured with django_googler installed."""
    from django.conf import settings

    assert settings.configured
    assert "django_googler" in settings.INSTALLED_APPS


def test_all_lazy_exports():
    """Test every public symbol listed in django_googler.__all__."""
    import django_googler

    for name in django_googler.__all__:
        obj = getattr(django_googler, name)
        assert obj is not None


def test_invalid_lazy_export_raises_attribute_error():
    """Accessing a nonexistent attribute raises AttributeError."""
    import django_googler

    with pytest.raises(AttributeError, match="has no attribute"):
        _ = django_googler.NonExistentThing


def test_urls_package_exports():
    """Test django_googler.urls package exports default urlpatterns."""
    import django_googler.urls as urls_pkg
    from django_googler.urls import api as api_urls
    from django_googler.urls import default as default_urls

    assert urls_pkg.urlpatterns == default_urls.urlpatterns
    assert api_urls.app_name == "django_googler_api"
    assert default_urls.app_name == "django_googler"
