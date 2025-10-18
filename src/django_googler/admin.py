"""
Django admin configuration for django_googler.

This module provides admin interface configuration for managing
Google OAuth tokens in the Django admin.
"""

from django.contrib import admin
from django.utils.html import format_html

from django_googler.models import GoogleOAuthToken


@admin.register(GoogleOAuthToken)
class GoogleOAuthTokenAdmin(admin.ModelAdmin):
    """Admin configuration for GoogleOAuthToken model."""

    list_display = [
        "user_email",
        "google_id",
        "token_status",
        "scope_count",
        "has_refresh_token",
        "expiry_display",
        "updated_at",
    ]

    list_filter = [
        "created_at",
        "updated_at",
        "token_expiry",
    ]

    search_fields = [
        "user__email",
        "user__username",
        "google_id",
    ]

    readonly_fields = [
        "user",
        "google_id",
        "created_at",
        "updated_at",
        "token_status_badge",
        "scopes_display",
        "access_token_preview",
        "refresh_token_preview",
    ]

    fieldsets = (
        (
            "User Information",
            {
                "fields": (
                    "user",
                    "google_id",
                    "token_status_badge",
                )
            },
        ),
        (
            "Token Information",
            {
                "fields": (
                    "access_token_preview",
                    "refresh_token_preview",
                    "token_expiry",
                )
            },
        ),
        (
            "Scopes",
            {
                "fields": ("scopes_display", "scopes"),
                "description": "OAuth scopes granted to this token",
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(
        description="User Email",
        ordering="user__email",
    )
    def user_email(self, obj):
        """Display user's email."""
        return obj.user.email

    @admin.display(description="Status")
    def token_status(self, obj):
        """Display token status as text."""
        if obj.is_valid:
            return "Valid"
        elif obj.is_expired():
            return "Expired"
        else:
            return "Invalid"

    @admin.display(description="Token Status")
    def token_status_badge(self, obj):
        """Display token status with color coding."""
        if obj.is_valid:
            color = "green"
            status = "✓ Valid"
        elif obj.is_expired():
            color = "orange"
            status = "⏱ Expired"
        else:
            color = "red"
            status = "✗ Invalid"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>', color, status
        )

    @admin.display(
        description="Can Refresh",
        boolean=True,
    )
    def has_refresh_token(self, obj):
        """Display if refresh token is available."""
        return bool(obj.refresh_token)

    @admin.display(description="Scopes")
    def scope_count(self, obj):
        """Display number of scopes."""
        scopes = obj.get_scopes_list()
        return len(scopes)

    @admin.display(
        description="Expires",
        ordering="token_expiry",
    )
    def expiry_display(self, obj):
        """Display token expiry time."""
        if not obj.token_expiry:
            return "Unknown"
        return obj.token_expiry.strftime("%Y-%m-%d %H:%M")

    @admin.display(description="Granted Scopes")
    def scopes_display(self, obj):
        """Display scopes as a formatted list."""
        scopes = obj.get_scopes_list()
        if not scopes:
            return "None"

        html = "<ul style='margin: 0; padding-left: 20px;'>"
        for scope in scopes:
            html += f"<li>{scope}</li>"
        html += "</ul>"

        return format_html(html)

    @admin.display(description="Access Token")
    def access_token_preview(self, obj):
        """Display a preview of the access token."""
        if not obj.access_token:
            return "None"

        # Show first 20 and last 10 characters
        token = obj.access_token
        if len(token) > 35:
            preview = f"{token[:20]}...{token[-10:]}"
        else:
            preview = token

        return format_html(
            '<code style="background: #f4f4f4; padding: 5px; '
            'border-radius: 3px;">{}</code>',
            preview,
        )

    @admin.display(description="Refresh Token")
    def refresh_token_preview(self, obj):
        """Display a preview of the refresh token."""
        if not obj.refresh_token:
            return "None"

        # Show first 20 and last 10 characters
        token = obj.refresh_token
        if len(token) > 35:
            preview = f"{token[:20]}...{token[-10:]}"
        else:
            preview = token

        return format_html(
            '<code style="background: #f4f4f4; padding: 5px; '
            'border-radius: 3px;">{}</code>',
            preview,
        )

    def has_delete_permission(self, request, obj=None):
        """Allow deletion of tokens."""
        return True

    def has_add_permission(self, request):
        """Disable adding tokens through admin (should come from OAuth flow)."""
        return False
