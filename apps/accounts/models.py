from functools import cached_property

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.core.crypto import EncryptedTextField
from apps.core.formatting import initials
from apps.tenancy.base import TenantModel


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        extra.setdefault("is_platform_staff", True)
        extra.setdefault("email_verified_at", timezone.now())
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractBaseUser, PermissionsMixin):
    """A person who signs in with an email address. Global: one user can belong to several organizations."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, help_text="E.164, e.g. +254712345678")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False, help_text="Can open the Django admin.")
    is_platform_staff = models.BooleanField(default=False, help_text="Works for the platform company (platform admin).")
    date_joined = models.DateTimeField(default=timezone.now)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    last_organization = models.ForeignKey("tenancy.Organization", null=True, blank=True, on_delete=models.SET_NULL,
                                          related_name="+")
    # Two-factor login (authenticator app). The secret is encrypted at rest; backup codes are stored hashed.
    totp_secret = EncryptedTextField(blank=True, default="")
    totp_enabled = models.BooleanField("two-factor login on", default=False)
    totp_last_step = models.BigIntegerField(null=True, blank=True, help_text="Last code step used (codes work once).")
    totp_backup_codes = models.JSONField(default=list, blank=True)
    totp_enabled_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name or self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return (self.full_name or self.email).split()[0]

    @property
    def initials(self):
        return initials(self.full_name or self.email)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    def active_memberships(self):
        from apps.tenancy.models import Membership

        return (self.memberships.filter(status=Membership.Status.ACTIVE)
                .exclude(organization__status="cancelled")
                .select_related("organization", "role").order_by("organization__name"))

    @cached_property
    def _membership_roles(self) -> list:
        return [m.role for m in self.active_memberships()]

    @property
    def two_factor_required(self) -> bool:
        """Platform staff and anyone holding a role that requires it (built-in Owner, Admin, Finance)."""
        if not settings.TWO_FACTOR_ENFORCED:
            return False
        return self.is_platform_staff or self.is_superuser or any(r.two_factor_required for r in self._membership_roles)

    @property
    def uses_two_factor(self) -> bool:
        return self.totp_enabled or self.two_factor_required

    @property
    def session_max_seconds(self) -> int | None:
        """The shortest "keep me signed in" limit among this user's roles (money roles sign out sooner)."""
        hours = [r.session_max_hours for r in self._membership_roles if r.session_max_hours]
        if self.is_platform_staff:
            hours.append(10)
        return min(hours) * 3600 if hours else None


class Department(TenantModel):
    name = models.CharField(max_length=100)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="unique_department_per_org")]

    def __str__(self):
        return self.name


class Role(TenantModel):
    """A role in one organization. Built-in roles take their permissions from apps.accounts.roles (always current,
    not editable); custom roles are built from RolePermission rows in the permission matrix."""

    class Scope(models.TextChoices):
        ALL = "all", "All records"
        DEPARTMENT = "department", "Their department's records"
        OWN = "own", "Only their own records"

    key = models.CharField(max_length=30, blank=True, help_text="Built-in role key; empty for custom roles.")
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=255, blank=True)
    is_builtin = models.BooleanField(default=False)
    two_factor_required = models.BooleanField(default=False)
    idle_timeout_minutes = models.PositiveIntegerField(default=0, help_text="Sign out after this long without activity (0 = never).")
    session_max_hours = models.PositiveIntegerField(default=0, help_text="Longest a sign-in lasts, even with “Keep me signed in” (0 = 30 days).")
    default_scope = models.CharField(max_length=12, choices=Scope.choices, default=Scope.ALL)
    sort_order = models.PositiveSmallIntegerField(default=100)

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="unique_role_name_per_org")]

    def __str__(self):
        return self.name


class RolePermission(TenantModel):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="permissions")
    permission = models.CharField(max_length=80, help_text="module.action, e.g. crm.edit or hr.view_salary")
    scope = models.CharField(max_length=12, choices=Role.Scope.choices, default=Role.Scope.ALL)

    class Meta:
        ordering = ["permission"]
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="unique_role_permission")]

    def __str__(self):
        return f"{self.role}: {self.permission}"
