from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import setup, tasks  # noqa: F401 - registers scheduled tasks
        from .modules import Module, register

        register(Module("dashboard", "Dashboard", "grid", "Your day at a glance.", "core:dashboard", ("core",),
                        core=True, actions=("view",), order=0))
        post_migrate.connect(setup.run, sender=self)
