from django.contrib.admin.apps import AdminConfig


class PlatformAdminConfig(AdminConfig):
    default_site = "apps.core.admin_tools.PlatformAdminSite"
