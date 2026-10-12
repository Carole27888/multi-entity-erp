"""Terminology: the words an organization uses for core records.

Resolution order: the organization's override → its sub-niche → its industry pack → the core default.
Templates: {% term "lead" %}, {% term "lead" plural=True %}, {% term "deal" lower=True %}.
Python:    term("lead", org=org, plural=True). Without `org` the current organization is used.
Core templates never hard-code industry words; a test enforces it.
"""

from __future__ import annotations

from .registry import Term, get

CORE_TERMS: dict[str, Term] = {
    "contact": Term("Contact"),
    "company": Term("Company", "Companies"),
    "customer": Term("Customer"),
    "lead": Term("Lead"),
    "deal": Term("Deal"),
    "pipeline": Term("Pipeline"),
    "product": Term("Product"),
    "service": Term("Service"),
    "catalogue": Term("Catalogue"),
    "quote": Term("Quote"),
    "order": Term("Order"),
    "invoice": Term("Invoice"),
    "project": Term("Project"),
    "task": Term("Task"),
    "ticket": Term("Ticket"),
    "appointment": Term("Appointment"),
    "resource": Term("Resource"),
    "staff": Term("Team member"),
    "supplier": Term("Supplier"),
    "partner": Term("Partner"),
    "location": Term("Location"),
}


def _resolve(org) -> dict[str, Term]:
    terms = dict(CORE_TERMS)
    if org is None:
        return terms
    pack = get(org.industry) if org.industry else None
    if pack:
        terms.update(pack.terminology)
        sub = pack.sub_niche(org.sub_niche) if org.sub_niche else None
        if sub:
            terms.update(sub.terminology)
    from apps.tenancy.context import tenant

    from .models import TerminologyOverride

    with tenant(org, activate_timezone=False):
        for o in TerminologyOverride.objects.all():
            terms[o.key] = Term(o.singular, o.plural)
    return terms


def terms_for(org) -> dict[str, Term]:
    """Cached on the organization instance (one per request/job)."""
    if org is None:
        return dict(CORE_TERMS)
    cached = getattr(org, "_terms_cache", None)
    if cached is None:
        cached = _resolve(org)
        org._terms_cache = cached
    return cached


def clear_cache(org) -> None:
    if org is not None and hasattr(org, "_terms_cache"):
        del org._terms_cache


def term(key: str, org=None, plural: bool = False, lower: bool = False) -> str:
    if org is None:
        from apps.tenancy.context import get_current_organization

        org = get_current_organization()
    t = terms_for(org).get(key) or Term(key.replace("_", " ").capitalize())
    word = t.plural_form if plural else t.singular
    return word.lower() if lower else word
