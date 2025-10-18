from django.urls import path

from .views import test_view

urlpatterns = [
    path("user/", test_view, name="test"),
]
