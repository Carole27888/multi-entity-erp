from django.contrib import admin

from .models import Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price_monthly", "annual_price", "max_users", "storage_gb", "custom_domain", "customer_portal",
                    "partner_portal", "api", "is_active")
    list_editable = ("is_active",)
