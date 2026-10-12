from django.contrib import admin

from apps.core.admin_tools import UnscopedRelationsMixin

from .models import Domain, Membership, Organization


class DomainInline(admin.TabularInline):
    model = Domain
    extra = 0
    readonly_fields = ("verification_token",)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "industry", "plan", "status", "trial_ends_at", "created_at")
    list_filter = ("status", "industry", "plan")
    search_fields = ("name", "slug")
    inlines = [DomainInline]


@admin.register(Membership)
class MembershipAdmin(UnscopedRelationsMixin, admin.ModelAdmin):
    list_display = ("user", "organization", "role", "status", "joined_at")
    list_filter = ("status",)
    search_fields = ("user__email", "organization__name")
    raw_id_fields = ("user", "organization")
    filter_horizontal = ("departments",)
