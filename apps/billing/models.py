"""Subscription plans for the platform itself. Limits live in the database (editable in Django admin) and are
enforced in code through Organization.plan_limits / has_feature. Full subscription billing arrives in phase 8."""

from decimal import Decimal

from django.db import models


class Plan(models.Model):
    FEATURES = ("public_subdomain", "custom_domain", "customer_portal", "partner_portal", "api")

    key = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=3, default="KES")
    price_monthly = models.DecimalField(max_digits=12, decimal_places=2)
    price_annual = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                       help_text="Leave empty for 10 × the monthly price (2 months free).")
    max_users = models.PositiveIntegerField(help_text="Active members plus open invitations.")
    max_industry_packs = models.PositiveIntegerField(default=1)
    storage_gb = models.PositiveIntegerField()
    public_bookings_per_month = models.PositiveIntegerField(null=True, blank=True, help_text="Empty = no limit.")
    public_subdomain = models.BooleanField(default=False, help_text="Public site on <slug>.<domain> (needs wildcard DNS).")
    custom_domain = models.BooleanField(default=False)
    customer_portal = models.BooleanField(default=False)
    partner_portal = models.BooleanField(default=False)
    api = models.BooleanField("API and webhooks", default=False)
    is_active = models.BooleanField(default=True, help_text="Offered to new sign-ups and upgrades.")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price_monthly"]

    def __str__(self):
        return self.name

    @property
    def annual_price(self) -> Decimal:
        return self.price_annual if self.price_annual is not None else self.price_monthly * 10

    def has_feature(self, feature: str) -> bool:
        return feature in self.FEATURES and bool(getattr(self, feature, False))
