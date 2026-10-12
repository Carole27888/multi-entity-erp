"""Applying industry packs to an organization. Safe to re-run: missing items are added, nothing the organization
created or edited is overwritten or deleted, and switching packs keeps all existing data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from django.db import transaction

from apps.tenancy.context import tenant

from . import registry
from .models import AppliedPack, CustomField, Pipeline, PipelineStage

# Other apps add their part of a pack (document templates, automations, dashboards…) with register_applier.
_APPLIERS: list[Callable] = []


def register_applier(func: Callable) -> Callable:
    """func(org, pack, sub_niche) — called inside the tenant context and transaction of apply_pack."""
    _APPLIERS.append(func)
    return func


class PackLimitError(Exception):
    """The organization's plan does not allow another industry pack."""


@dataclass
class ApplyResult:
    pack: str
    modules_added: list = field(default_factory=list)
    pipelines_created: list = field(default_factory=list)
    stages_added: int = 0
    fields_created: int = 0


def apply_pack(org, pack_key: str, sub_niche: str = "", primary: bool = True, modules: list[str] | None = None) -> ApplyResult:
    """Apply `pack_key` to `org`. `modules` replaces the pack's suggested module list (the onboarding choice)."""
    pack = registry.get(pack_key)
    if pack is None:
        raise KeyError(f"Unknown industry pack '{pack_key}'")
    result = ApplyResult(pack=pack_key)
    with tenant(org, activate_timezone=False), transaction.atomic():
        already = AppliedPack.objects.filter(pack_key=pack_key).exists()
        if not already:
            plan = org.effective_plan
            limit = plan.max_industry_packs if plan else 1
            if AppliedPack.objects.count() >= limit:
                raise PackLimitError(f"Your plan allows {limit} industry pack{'s' if limit != 1 else ''}.")

        if primary:
            AppliedPack.objects.filter(is_primary=True).exclude(pack_key=pack_key).update(is_primary=False)
            org.industry, org.sub_niche = pack_key, sub_niche
        wanted = modules if modules is not None else pack.default_modules(sub_niche)
        enabled = list(org.enabled_modules or [])
        for key in wanted:
            if key not in enabled:
                enabled.append(key)
                result.modules_added.append(key)
        org.enabled_modules = enabled
        org.save(update_fields=["industry", "sub_niche", "enabled_modules", "updated_at"])

        for pdef in pack.pipelines:
            pipeline, created = Pipeline.objects.get_or_create(
                entity=pdef.entity, key=pdef.key,
                defaults={"name": pdef.name, "is_default": pdef.is_default and not Pipeline.objects.filter(
                    entity=pdef.entity, is_default=True).exists(), "pack_key": pack_key})
            if created:
                result.pipelines_created.append(pdef.key)
            if pipeline.customised:
                continue
            existing = set(pipeline.stages.values_list("key", flat=True))
            for order, sdef in enumerate(pdef.stages, start=1):
                if sdef.key in existing:
                    continue
                PipelineStage.objects.create(pipeline=pipeline, key=sdef.key, name=sdef.name, colour=sdef.colour,
                                             order=order * 10, probability=sdef.probability, is_won=sdef.is_won,
                                             is_lost=sdef.is_lost)
                result.stages_added += 1

        for order, fdef in enumerate(pack.custom_fields, start=1):
            _, created = CustomField.objects.get_or_create(
                entity=fdef.entity, key=fdef.key,
                defaults={"label": fdef.label, "type": fdef.type, "options": list(fdef.options), "required": fdef.required,
                          "help_text": fdef.help, "section": fdef.section, "order": order * 10, "pack_key": pack_key})
            result.fields_created += int(created)

        AppliedPack.objects.update_or_create(pack_key=pack_key, defaults={
            "sub_niche": sub_niche, "version": pack.version, "is_primary": primary or not AppliedPack.objects.exists()})

        for applier in _APPLIERS:
            applier(org, pack, sub_niche)
    from .terms import clear_cache

    clear_cache(org)
    return result


def reapply_all(org) -> list[ApplyResult]:
    """Re-run every pack the organization has (adds what newer pack versions introduced)."""
    with tenant(org, activate_timezone=False):
        applied = list(AppliedPack.objects.all())
    return [apply_pack(org, a.pack_key, a.sub_niche, primary=a.is_primary, modules=[]) for a in applied]
