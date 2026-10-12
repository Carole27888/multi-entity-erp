from django.apps import AppConfig


class TenancyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tenancy"
    verbose_name = "Organizations"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import setup

        post_migrate.connect(setup.run, sender=self)
