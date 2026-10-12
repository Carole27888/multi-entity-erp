"""Organizations (tenants), their domains, memberships and invitations."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.core.models import TimeStampedModel

from .base import TenantModel

# First path segments that can never be an organization slug (they are platform URLs).
RESERVED_SLUGS = {
    "accounts", "admin", "api", "app", "billing", "django-admin", "files", "health", "help", "invite", "login",
    "logout", "manifest.webmanifest", "media", "media-public", "offline", "onboarding", "orgs", "platform",
    "portal", "pricing", "privacy", "s", "settings", "signup", "static", "status", "support", "sw.js", "terms",
    "webhooks", "www", "favicon.ico", "robots.txt", "sitemap.xml", "_media_not_served",
}

slug_validator = RegexValidator(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$",
                                "Use 2–50 lowercase letters, numbers or hyphens, starting and ending with a letter or number.")
colour_validator = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use a hex colour like #134E4A.")


def org_logo_path(instance, filename):
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "png").lower()[:5]
    return f"{instance.pk or 'new'}/branding/logo-{secrets.token_hex(6)}.{ext}"


class Organization(TimeStampedModel):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Payment overdue"
        READ_ONLY = "read_only", "Read-only (unpaid)"
        SUSPENDED = "suspended", "Suspended"
        CANCELLED = "cancelled", "Cancelled"

    RUNNING_STATUSES = (Status.TRIAL, Status.ACTIVE, Status.PAST_DUE, Status.READ_ONLY)
    WRITABLE_STATUSES = (Status.TRIAL, Status.ACTIVE, Status.PAST_DUE)

    class TeamSize(models.TextChoices):
        SOLO = "1", "Just me"
        SMALL = "2-5", "2–5 people"
        MEDIUM = "6-20", "6–20 people"
        LARGE = "21-50", "21–50 people"
        XL = "51+", "More than 50"

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=50, unique=True, validators=[slug_validator])
    legal_name = models.CharField(max_length=200, blank=True)
    industry = models.CharField(max_length=40, blank=True, help_text="Primary industry pack key.")
    sub_niche = models.CharField(max_length=40, blank=True)
    team_size = models.CharField(max_length=10, choices=TeamSize.choices, blank=True)
    country = models.ForeignKey("core.Country", on_delete=models.PROTECT, related_name="+", default="KE")
    currency = models.CharField(max_length=3, default="KES")
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    logo = models.ImageField(upload_to=org_logo_path, blank=True)
    brand_colour = models.CharField(max_length=7, default="#134E4A", validators=[colour_validator])
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.CharField(max_length=255, blank=True)
    kra_pin = models.CharField("KRA PIN", max_length=20, blank=True)
    website_url = models.URLField(blank=True)

    plan = models.ForeignKey("billing.Plan", null=True, blank=True, on_delete=models.PROTECT, related_name="organizations")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL, db_index=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    suspended_reason = models.CharField(max_length=255, blank=True)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    enabled_modules = models.JSONField(default=list, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    # --- URLs -------------------------------------------------------------------------------------
    @property
    def app_path(self) -> str:
        """Staff app home, e.g. /savannah-trails/ (path routing)."""
        from .routing import org_app_url

        return org_app_url(self)

    @property
    def public_url(self) -> str:
        from .routing import org_public_url

        return org_public_url(self)

    # --- State ------------------------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self.status in self.RUNNING_STATUSES

    @property
    def is_writable(self) -> bool:
        return self.status in self.WRITABLE_STATUSES

    @property
    def trial_days_left(self) -> int | None:
        if self.status != self.Status.TRIAL or not self.trial_ends_at:
            return None
        return max((self.trial_ends_at - timezone.now()).days + 1, 0)

    def start_trial(self, days: int | None = None):
        self.status = self.Status.TRIAL
        self.trial_ends_at = timezone.now() + timedelta(days=days or settings.TRIAL_DAYS)

    # --- Plan ---------------------------------------------------------------------------------------
    @property
    def effective_plan(self):
        """During the trial the organization gets TRIAL_PLAN's features."""
        from apps.billing.models import Plan

        if self.status == self.Status.TRIAL:
            trial = Plan.objects.filter(key=settings.TRIAL_PLAN).first()
            if trial:
                return trial
        return self.plan

    def has_feature(self, feature: str) -> bool:
        plan = self.effective_plan
        return bool(plan and plan.has_feature(feature))

    def is_module_enabled(self, key: str) -> bool:
        from apps.core.modules import is_enabled_for

        return is_enabled_for(self, key)

    @property
    def initials(self) -> str:
        from apps.core.formatting import initials

        return initials(self.name)


class Domain(models.Model):
    """A host name that serves an organization's public site: its subdomain, or a custom domain it verified."""

    class Kind(models.TextChoices):
        SUBDOMAIN = "subdomain", "Platform subdomain"
        CUSTOM = "custom", "Custom domain"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CUSTOM)
    verification_token = models.CharField(max_length=64, default="", blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["hostname"]

    def __str__(self):
        return self.hostname

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower().rstrip(".")
        if not self.verification_token:
            self.verification_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class Membership(models.Model):
    """A user's place in an organization. One user can belong to several organizations."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DISABLED = "disabled", "Disabled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    # RESTRICT: a role in use can't be deleted, but deleting the whole organization still works.
    role = models.ForeignKey("accounts.Role", on_delete=models.RESTRICT, related_name="memberships")
    departments = models.ManyToManyField("accounts.Department", blank=True, related_name="members")
    title = models.CharField("job title", max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    joined_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["organization__name"]
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="unique_membership")]

    def __str__(self):
        return f"{self.user} @ {self.organization}"

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE


def _invite_token():
    return secrets.token_urlsafe(32)


def _invite_expiry():
    return timezone.now() + timedelta(days=7)


class Invitation(TenantModel):
    email = models.EmailField()
    role = models.ForeignKey("accounts.Role", on_delete=models.CASCADE, related_name="+")
    token = models.CharField(max_length=64, unique=True, default=_invite_token, editable=False)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(default=_invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    @property
    def is_open(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > timezone.now()
