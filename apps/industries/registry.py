"""Industry Pack registry.

A pack only switches modules on and configures them for an industry: terminology, pipeline stages, custom fields,
document templates, dashboard widgets, reports, automation templates, sample data and the getting-started
checklist. Industry-specific features live in ordinary Django apps (apps/tourism, apps/realestate) that a pack
enables. One file per industry in apps/industries/packs/<key>.py defines PACK and calls register().

Applying a pack is done by apps.industries.services.apply_pack (idempotent, never overwrites admin edits).
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Term:
    singular: str
    plural: str = ""

    @property
    def plural_form(self) -> str:
        return self.plural or (self.singular + "s")


@dataclass(frozen=True)
class SubNiche:
    key: str
    name: str
    description: str = ""
    terminology: dict = field(default_factory=dict)  # overrides the pack's terms
    modules_default: tuple = ()  # added to the pack's defaults


@dataclass(frozen=True)
class Stage:
    key: str
    name: str
    colour: str = "#64748B"
    probability: int = 0
    is_won: bool = False
    is_lost: bool = False


@dataclass(frozen=True)
class PipelineDef:
    key: str
    name: str
    entity: str  # "deal" or "lead"
    stages: tuple
    is_default: bool = True


@dataclass(frozen=True)
class CustomFieldDef:
    entity: str  # contact | company | lead | deal | product | order
    key: str
    label: str
    type: str = "text"  # see CustomField.Type
    options: tuple = ()
    required: bool = False
    help: str = ""
    section: str = ""


@dataclass(frozen=True)
class DocTemplateDef:
    kind: str  # quote | invoice | receipt | contract | voucher | proposal | job_card | …
    key: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class AutomationDef:
    key: str
    name: str
    trigger: str
    description: str = ""


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    title: str
    description: str = ""
    url_name: str = ""  # tenant URL name; the item is hidden until that page exists
    auto: str = ""  # name of a detector in apps.industries.checklist.DETECTORS (ticks itself)


@dataclass(frozen=True)
class IndustryPack:
    key: str
    name: str
    icon: str
    tagline: str
    sub_niches: tuple = ()
    modules_default: tuple = ()
    modules_optional: tuple = ()
    terminology: dict = field(default_factory=dict)
    pipelines: tuple = ()
    custom_fields: tuple = ()
    document_templates: tuple = ()
    dashboard_widgets: tuple = ()
    reports: tuple = ()
    automation_templates: tuple = ()
    checklist: tuple = ()
    catalogue_kind: str = "products and services"  # what the public site publishes
    deep_module: str = ""  # app key that gives this industry its own features ("" = configuration pack only)
    planned: str = ""  # what the deep module will add later (shown in ASSUMPTIONS.md and Settings)
    version: int = 1
    keywords: tuple = ()  # extra words for the onboarding search

    def sub_niche(self, key: str) -> SubNiche | None:
        return next((s for s in self.sub_niches if s.key == key), None)

    def default_modules(self, sub_niche: str = "") -> list[str]:
        mods = list(self.modules_default)
        sn = self.sub_niche(sub_niche) if sub_niche else None
        if sn:
            mods += [m for m in sn.modules_default if m not in mods]
        return mods

    def search_text(self) -> str:
        words = [self.name, self.tagline, *self.keywords, *(s.name for s in self.sub_niches)]
        return " ".join(words).lower()


_PACKS: dict[str, IndustryPack] = {}
_loaded = False


def register(pack: IndustryPack) -> IndustryPack:
    _PACKS[pack.key] = pack
    return pack


def _load():
    global _loaded
    if _loaded:
        return
    from . import packs

    for info in pkgutil.iter_modules(packs.__path__):
        importlib.import_module(f"{packs.__name__}.{info.name}")
    _loaded = True


def get(key: str) -> IndustryPack | None:
    _load()
    return _PACKS.get(key)


def all_packs() -> list[IndustryPack]:
    """Packs in display order (generic last)."""
    _load()
    return sorted(_PACKS.values(), key=lambda p: (p.key == "generic", p.name))


def choices() -> list[tuple[str, str]]:
    return [(p.key, p.name) for p in all_packs()]
