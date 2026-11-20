"""
Django admin configuration for django_googler.

This module provides admin interface configuration for managing
Google OAuth tokens in the Django admin.
"""

from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join

from django_googler.models import GoogleOAuthToken, get_user_identifier
from django_googler.services import GoogleOAuthService, _user_model_has_field


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

    list_select_related = ("user",)

    list_filter = [
        "created_at",
        "updated_at",
        "token_expiry",
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

    actions = ["refresh_selected_tokens", "revoke_selected_tokens"]

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

    def get_search_fields(self, request):
        """Build search_fields dynamically so custom user models never error."""
        fields = ["google_id"]
        if _user_model_has_field("email"):
            fields.insert(0, "user__email")
        if _user_model_has_field("username"):
            fields.insert(1 if "user__email" in fields else 0, "user__username")
        return fields

    @admin.action(description="Refresh selected Google OAuth tokens")
    def refresh_selected_tokens(self, request, queryset):
        """Refresh selected OAuth tokens that have refresh tokens."""
        refreshed = 0
        failed = 0
        for token in queryset.select_related("user"):
            try:
                GoogleOAuthService.refresh_user_token(token)
                refreshed += 1
            except Exception:
                failed += 1
        if refreshed:
            self.message_user(
                request,
                f"Refreshed {refreshed} token(s).",
                level=messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                f"Failed to refresh {failed} token(s).",
                level=messages.WARNING,
            )

    @admin.action(description="Revoke and delete selected Google OAuth tokens")
    def revoke_selected_tokens(self, request, queryset):
        """Revoke selected OAuth tokens with Google and delete them."""
        revoked = 0
        for token in queryset.select_related("user"):
            if GoogleOAuthService.revoke_user_token(token.user):
                revoked += 1
        self.message_user(
            request,
            f"Revoked and deleted {revoked} token(s).",
            level=messages.SUCCESS,
        )

    @admin.display(
        description="User",
        ordering="user",
    )
    def user_email(self, obj):
        """Display user's email or fallback identifier."""
        return get_user_identifier(obj.user)

    @admin.display(description="Status")
    def token_status(self, obj):
        """Display token status as text."""
        if obj.is_valid:
            return "Valid"
        if obj.is_expired():
            return "Expired"
        return "Invalid"

    @admin.display(description="Token Status")
    def token_status_badge(self, obj):
        """Display token status with color coding."""
        if obj.is_valid:
            color = "green"
            status_label = "✓ Valid"
        elif obj.is_expired():
            color = "orange"
            status_label = "⏱ Expired"
        else:
            color = "red"
            status_label = "✗ Invalid"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status_label,
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
        return len(obj.get_scopes_list())

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
        """Display scopes safely as an escaped HTML list."""
        scopes = obj.get_scopes_list()
        if not scopes:
            return "None"

        items = format_html_join("", "<li>{}</li>", ((scope,) for scope in scopes))
        return format_html(
            '<ul style="margin: 0; padding-left: 20px;">{}</ul>',
            items,
        )

    @admin.display(description="Access Token")
    def access_token_preview(self, obj):
        """Display a truncated preview of the access token."""
        if not obj.access_token:
            return "None"

        token = obj.access_token
        preview = f"{token[:20]}...{token[-10:]}" if len(token) > 35 else token

        return format_html(
            '<code style="background: #f4f4f4; padding: 5px; '
            'border-radius: 3px;">{}</code>',
            preview,
        )

    @admin.display(description="Refresh Token")
    def refresh_token_preview(self, obj):
        """Display a truncated preview of the refresh token."""
        if not obj.refresh_token:
            return "None"

        token = obj.refresh_token
        preview = f"{token[:20]}...{token[-10:]}" if len(token) > 35 else token

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
