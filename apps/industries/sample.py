"""Sample data loaders. Each app that owns records registers a loader for them (CRM contacts and leads,
catalogue items, tourism packages…); the pack's sample data is then loaded by the registered loaders.

    @register_loader
    def crm_sample(org, pack): ...   # runs inside `with tenant(org)`, must be idempotent

Phase 1 has no business records yet, so no loaders are registered: an organization that asked for sample data
is flagged (Organization.settings["sample_data_requested"]) and gets it when the loaders ship.
"""

from __future__ import annotations

from typing import Callable

from apps.tenancy.context import tenant

from . import registry

_LOADERS: list[Callable] = []


def register_loader(func: Callable) -> Callable:
    _LOADERS.append(func)
    return func


def available() -> bool:
    return bool(_LOADERS)


def load(org) -> int:
    pack = registry.get(org.industry)
    if pack is None:
        return 0
    with tenant(org, activate_timezone=False):
        for loader in _LOADERS:
            loader(org, pack)
    if _LOADERS:
        org.settings = {**org.settings, "sample_data_loaded": True}
        org.save(update_fields=["settings"])
    return len(_LOADERS)
