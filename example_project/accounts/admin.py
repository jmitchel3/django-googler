from django.contrib import admin

# Register your models here.
from accounts.models import MyUser


@admin.register(MyUser)
class MyUserAdmin(admin.ModelAdmin):
    list_display = ["email", "is_active", "is_admin", "last_login"]
    list_filter = ["is_active", "is_admin"]
    search_fields = ["email"]
    ordering = ["email"]
    readonly_fields = ["email", "is_active", "is_admin"]
    fields = ["email", "is_active", "is_admin"]
    model = MyUser
    list_per_page = 10
    list_max_show_all = 100
    list_editable = ["last_login", "is_admin"]
    list_display_links = ["email"]
    list_select_related = []
