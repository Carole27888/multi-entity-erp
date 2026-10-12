"""Django admin is a platform tool (/django-admin/, platform staff only). Tenant models are shown across
organizations, so their querysets and FK widgets use the unscoped manager."""

from django.contrib import admin

from apps.tenancy.base import is_tenant_model


class UnscopedRelationsMixin:
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if is_tenant_model(db_field.related_model):
            kwargs.setdefault("queryset", db_field.related_model.unscoped.all())
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if is_tenant_model(db_field.related_model):
            kwargs.setdefault("queryset", db_field.related_model.unscoped.all())
        return super().formfield_for_manytomany(db_field, request, **kwargs)


class TenantModelAdmin(UnscopedRelationsMixin, admin.ModelAdmin):
    list_display = ("__str__", "organization")
    list_filter = ("organization",)

    def get_queryset(self, request):
        return self.model.unscoped.select_related("organization")


class PlatformAdminSite(admin.AdminSite):
    """Only platform staff may open the Django admin."""

    def has_permission(self, request):
        return bool(request.user.is_active and request.user.is_staff and request.user.is_platform_staff)
