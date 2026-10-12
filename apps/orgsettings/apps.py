from django.apps import AppConfig


class OrgSettingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orgsettings"
    verbose_name = "Organization settings"

    def ready(self):
        from apps.core.modules import Module, NavItem, register

        register(Module(
            "settings", "Settings", "settings", "Organization profile, branding, team, roles and modules.",
            "orgsettings:index", ("orgsettings",), core=True, order=900,
            actions=("view", "edit"),
            extra_permissions={"manage_team": "Invite and manage teammates", "manage_roles": "Create and edit roles"},
            nav=[
                NavItem("Settings", "orgsettings:index", "settings"),
                NavItem("Profile & branding", "orgsettings:profile", "image", section="Organization"),
                NavItem("Modules", "orgsettings:modules", "grid", section="Organization"),
                NavItem("Team", "orgsettings:members", "users", section="People", permission="settings.manage_team",
                        match=("orgsettings:member_edit",)),
                NavItem("Roles & permissions", "orgsettings:roles", "key", section="People",
                        permission="settings.manage_roles", match=("orgsettings:role_edit", "orgsettings:role_new",
                                                                   "orgsettings:role_view")),
                NavItem("Departments", "orgsettings:departments", "columns", section="People",
                        permission="settings.manage_team"),
            ],
            bottom_nav=[
                NavItem("Home", "core:dashboard", "grid"),
                NavItem("Settings", "orgsettings:index", "settings"),
                NavItem("Team", "orgsettings:members", "users", permission="settings.manage_team"),
                NavItem("Roles", "orgsettings:roles", "key", permission="settings.manage_roles"),
            ],
        ))
