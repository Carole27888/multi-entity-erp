"""Per-organization configuration created by industry packs (and edited by tenant admins)."""

from django.db import models
from django.utils import timezone

from apps.core.models import TenantTimeStampedModel
from apps.tenancy.base import TenantModel


class AppliedPack(TenantModel):
    pack_key = models.CharField(max_length=40)
    sub_niche = models.CharField(max_length=40, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_primary = models.BooleanField(default=False)
    applied_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-is_primary", "applied_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "pack_key"], name="unique_applied_pack")]

    def __str__(self):
        return self.pack_key

    @property
    def pack(self):
        from .registry import get

        return get(self.pack_key)


class TerminologyOverride(TenantModel):
    """An organization's own word for a term (wins over the pack and the core default)."""

    key = models.CharField(max_length=40)
    singular = models.CharField(max_length=60)
    plural = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["key"]
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="unique_term_override")]

    def __str__(self):
        return f"{self.key} → {self.singular}"


class CustomField(TenantTimeStampedModel):
    """An extra field on a core record. Values live in the record's `custom` JSON column under `key`."""

    class Entity(models.TextChoices):
        CONTACT = "contact", "Contact"
        COMPANY = "company", "Company"
        LEAD = "lead", "Lead"
        DEAL = "deal", "Deal"
        PRODUCT = "product", "Product / service"
        ORDER = "order", "Order / booking"

    class Type(models.TextChoices):
        TEXT = "text", "Short text"
        TEXTAREA = "textarea", "Long text"
        NUMBER = "number", "Number"
        MONEY = "money", "Amount"
        DATE = "date", "Date"
        CHOICE = "choice", "Pick one"
        MULTI = "multi", "Pick several"
        BOOL = "bool", "Yes / no"
        EMAIL = "email", "Email"
        PHONE = "phone", "Phone"
        URL = "url", "Web address"

    entity = models.CharField(max_length=20, choices=Entity.choices)
    key = models.SlugField(max_length=40)
    label = models.CharField(max_length=80)
    type = models.CharField(max_length=10, choices=Type.choices, default=Type.TEXT)
    options = models.JSONField(default=list, blank=True, help_text="Choices for pick-one / pick-several fields.")
    required = models.BooleanField(default=False)
    help_text = models.CharField(max_length=200, blank=True)
    section = models.CharField(max_length=60, blank=True)
    order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    pack_key = models.CharField(max_length=40, blank=True, help_text="The pack that created it (empty = added by the organization).")
    customised = models.BooleanField(default=False, help_text="Edited by the organization; re-applying a pack leaves it alone.")

    class Meta:
        ordering = ["entity", "order", "label"]
        constraints = [models.UniqueConstraint(fields=["organization", "entity", "key"], name="unique_custom_field")]

    def __str__(self):
        return f"{self.get_entity_display()}: {self.label}"


class Pipeline(TenantModel):
    entity = models.CharField(max_length=20, default="deal")
    key = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    is_default = models.BooleanField(default=False)
    pack_key = models.CharField(max_length=40, blank=True)
    customised = models.BooleanField(default=False)

    class Meta:
        ordering = ["entity", "-is_default", "name"]
        constraints = [models.UniqueConstraint(fields=["organization", "entity", "key"], name="unique_pipeline")]

    def __str__(self):
        return self.name


class PipelineStage(TenantModel):
    pipeline = models.ForeignKey(Pipeline, on_delete=models.CASCADE, related_name="stages")
    key = models.SlugField(max_length=40)
    name = models.CharField(max_length=60)
    colour = models.CharField(max_length=7, default="#64748B")
    order = models.PositiveSmallIntegerField(default=0)
    probability = models.PositiveSmallIntegerField(default=0, help_text="Chance of winning at this stage, %.")
    is_won = models.BooleanField(default=False)
    is_lost = models.BooleanField(default=False)

    class Meta:
        ordering = ["pipeline", "order"]
        constraints = [models.UniqueConstraint(fields=["pipeline", "key"], name="unique_stage_per_pipeline")]

    def __str__(self):
        return self.name


class ChecklistProgress(TenantModel):
    item_key = models.CharField(max_length=60)
    done_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "item_key"], name="unique_checklist_item")]
