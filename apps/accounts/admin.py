from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.core.admin_tools import TenantModelAdmin

from .models import Department, Role, RolePermission, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "full_name", "is_platform_staff", "totp_enabled", "is_active", "date_joined")
    list_filter = ("is_platform_staff", "is_active", "totp_enabled")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("date_joined", "last_login", "totp_enabled_at", "email_verified_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "email_verified_at")}),
        ("Access", {"fields": ("is_active", "is_platform_staff", "is_staff", "is_superuser")}),
        ("Two-factor login", {"fields": ("totp_enabled", "totp_enabled_at")}),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),)
    filter_horizontal = ()


@admin.register(Role)
class RoleAdmin(TenantModelAdmin):
    list_display = ("name", "organization", "is_builtin", "two_factor_required")


admin.site.register(RolePermission, TenantModelAdmin)
admin.site.register(Department, TenantModelAdmin)
