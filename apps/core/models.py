from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.tenancy.base import TenantModel

from .middleware import get_current_user


class TimeStampedModel(models.Model):
    """Who created/changed a row and when."""

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False, on_delete=models.SET_NULL, related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False, on_delete=models.SET_NULL, related_name="+",
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user is not None and user.is_authenticated:
            if self._state.adding and not self.created_by_id:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class TenantTimeStampedModel(TenantModel, TimeStampedModel):
    """The usual base for business records: organization-scoped, with created/updated stamps."""

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Adds deleted_at. Combine with a manager that hides deleted rows where a model needs it."""

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])


# --- Global reference data (seeded by apps.core.setup on post_migrate) -------------------------------

class Currency(models.Model):
    code = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=8, blank=True)
    decimals = models.PositiveSmallIntegerField(default=2)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "currencies"

    def __str__(self):
        return f"{self.code} · {self.name}"


class Country(models.Model):
    """A country template. Kenya ships with tax, payroll and chart-of-accounts templates; others can be added."""

    code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=80)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name="+")
    timezone = models.CharField(max_length=64)
    dial_code = models.CharField(max_length=6, help_text="e.g. +254")
    default_vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    has_templates = models.BooleanField(default=False, help_text="Tax, payroll and chart-of-accounts templates exist.")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


# --- Per-organization numbering ---------------------------------------------------------------------

class Sequence(TenantModel):
    """Gap-safe document numbers per organization (INV-0001, RCT-0001). Never MAX(id)+1."""

    key = models.CharField(max_length=40)
    prefix = models.CharField(max_length=12)
    padding = models.PositiveSmallIntegerField(default=4)
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="unique_sequence_per_org")]

    def __str__(self):
        return f"{self.prefix} ({self.last_value})"

    @classmethod
    def next(cls, key: str, prefix: str | None = None, padding: int = 4) -> str:
        with transaction.atomic():
            seq, _ = cls.objects.select_for_update().get_or_create(
                key=key, defaults={"prefix": prefix or key.upper(), "padding": padding}
            )
            seq.last_value += 1
            seq.save(update_fields=["last_value"])
            return f"{seq.prefix}-{seq.last_value:0{seq.padding}d}"


# --- Audit trail -------------------------------------------------------------------------------------

class AuditLog(models.Model):
    """Actions that are not plain model saves (logins, exports, approvals, impersonation, suspensions).

    organization is empty for platform-level events. Read it with AuditLog.for_org(org) in tenant code.
    """

    organization = models.ForeignKey("tenancy.Organization", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    impersonator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=80, db_index=True)
    target = models.CharField(max_length=200, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"

    @classmethod
    def for_org(cls, org):
        return cls.objects.filter(organization=org)


# --- Job system ---------------------------------------------------------------------------------------

class Job(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    organization = models.ForeignKey("tenancy.Organization", null=True, blank=True, on_delete=models.CASCADE, related_name="+",
                                     help_text="The job runs as this organization (empty = platform job).")
    task_name = models.CharField(max_length=120, db_index=True)
    kwargs = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    run_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["run_at", "id"]
        indexes = [models.Index(fields=["status", "run_at"])]

    def __str__(self):
        return f"{self.task_name} [{self.status}]"


class ScheduleState(models.Model):
    """Last time each schedule ran (per organization for per-org schedules), so run_jobs knows what is due."""

    name = models.CharField(max_length=120)
    organization = models.ForeignKey("tenancy.Organization", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "organization"], name="unique_schedule_state")]

    def __str__(self):
        return self.name


class JobLock(models.Model):
    """Single-row database lock so two cron runs never overlap."""

    name = models.CharField(max_length=40, unique=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    owner = models.CharField(max_length=64, blank=True)


class JobRunnerHeartbeat(models.Model):
    """One row per run_jobs invocation; used for the 'cron has not run' warning."""

    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    jobs_run = models.PositiveIntegerField(default=0)
    jobs_failed = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]


# --- Files ---------------------------------------------------------------------------------------------

def org_upload_to(subdir: str):
    """upload_to for tenant files: MEDIA_ROOT/<org-id>/<subdir>/<yyyy>/<mm>/<random>.<ext>."""

    def _path(instance, filename):
        import secrets

        ext = ""
        if "." in filename:
            ext = "." + "".join(ch for ch in filename.rsplit(".", 1)[-1].lower() if ch.isalnum())[:8]
        org_id = instance.organization_id
        if org_id is None:  # file saved before the row: use the current organization (never a shared folder)
            from apps.tenancy.context import require_organization

            org_id = require_organization().pk
        now = timezone.now()
        return f"{org_id}/{subdir}/{now:%Y}/{now:%m}/{secrets.token_hex(12)}{ext}"

    _path.__qualname__ = _path.__name__ = f"org_upload_to_{subdir.replace('/', '_')}"
    return _path


def _attachment_path(instance, filename):
    return org_upload_to("attachments")(instance, filename)


class Attachment(TenantTimeStampedModel):
    """A file attached to any record. Served only by core:file (permission-checked), never by a public URL."""

    file = models.FileField(upload_to=_attachment_path, max_length=255)
    name = models.CharField(max_length=200)
    size = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    content_type = models.ForeignKey("contenttypes.ContentType", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    permission = models.CharField(max_length=80, default="dashboard.view",
                                  help_text="Permission needed to download it, e.g. crm.view or hr.view_salary.")
    confidential = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        return self.name
