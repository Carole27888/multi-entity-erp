"""Default plans (post_migrate). Created once with get_or_create; edits made in Django admin are never overwritten."""

from decimal import Decimal

PLANS = [
    {"key": "starter", "name": "Starter", "sort_order": 1, "price_monthly": Decimal("2500"),
     "description": "For small teams getting started.",
     "max_users": 3, "max_industry_packs": 1, "storage_gb": 2, "public_bookings_per_month": 50},
    {"key": "growth", "name": "Growth", "sort_order": 2, "price_monthly": Decimal("7500"),
     "description": "Your own domain and a customer portal.",
     "max_users": 10, "max_industry_packs": 2, "storage_gb": 10, "public_bookings_per_month": 500,
     "public_subdomain": True, "custom_domain": True, "customer_portal": True},
    {"key": "business", "name": "Business", "sort_order": 3, "price_monthly": Decimal("20000"),
     "description": "Partner portal, API and webhooks for larger operations.",
     "max_users": 30, "max_industry_packs": 5, "storage_gb": 50, "public_bookings_per_month": None,
     "public_subdomain": True, "custom_domain": True, "customer_portal": True, "partner_portal": True, "api": True},
]


def run(sender=None, **kwargs):
    from .models import Plan

    for data in PLANS:
        data = dict(data)
        Plan.objects.get_or_create(key=data.pop("key"), defaults=data)
