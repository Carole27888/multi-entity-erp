from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.billing"
    verbose_name = "Plans & billing"

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import setup

        post_migrate.connect(setup.run, sender=self)
