"""The getting-started checklist: core items for everyone plus the industry pack's own items.

An item is done when its detector says so (e.g. a logo was uploaded) or when someone ticks it.
Items whose page does not exist yet (url_name cannot be reversed) are hidden.
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

from . import registry
from .models import ChecklistProgress
from .registry import ChecklistItem


def _has_logo(org, request):
    return bool(org.logo)


def _has_brand(org, request):
    return org.brand_colour.upper() != "#134E4A"


def _invited(org, request):
    from apps.tenancy.models import Invitation, Membership

    return Membership.objects.filter(organization=org).count() > 1 or Invitation.objects.exists()


def _two_factor(org, request):
    return bool(request and request.user.is_authenticated and request.user.totp_enabled)


def _verified(org, request):
    return bool(request and request.user.is_authenticated and request.user.email_verified)


DETECTORS = {"logo": _has_logo, "brand": _has_brand, "invite": _invited, "two_factor": _two_factor, "verified": _verified}

CORE_CHECKLIST = (
    ChecklistItem("verify_email", "Confirm your email address", "So password resets and alerts reach you.", auto="verified"),
    ChecklistItem("logo", "Upload your logo", "It appears in the app, on documents and on your website.",
                  url_name="orgsettings:profile", auto="logo"),
    ChecklistItem("brand", "Choose your brand colour", "Buttons, menus and documents use it.",
                  url_name="orgsettings:profile", auto="brand"),
    ChecklistItem("invite", "Invite your team", "Give each person a role so they see what they need.",
                  url_name="orgsettings:members", auto="invite"),
    ChecklistItem("two_factor", "Turn on two-factor login", "Protects your account with a code from your phone.",
                  url_name="accounts:security", auto="two_factor"),
)


def _url(item: ChecklistItem) -> str | None:
    if not item.url_name:
        return ""
    if item.url_name.startswith("accounts:"):
        from apps.tenancy.routing import reverse_global

        return reverse_global(item.url_name)
    try:
        return reverse(item.url_name)
    except NoReverseMatch:
        return None


def items_for(org, request=None) -> list[dict]:
    pack = registry.get(org.industry) if org.industry else None
    items = list(CORE_CHECKLIST) + list(pack.checklist if pack else ())
    ticked = set(ChecklistProgress.objects.values_list("item_key", flat=True))
    out = []
    for item in items:
        url = _url(item)
        if url is None:
            continue  # its page arrives in a later phase
        detector = DETECTORS.get(item.auto)
        done = item.key in ticked or bool(detector and detector(org, request))
        out.append({"key": item.key, "title": item.title, "description": item.description, "url": url, "done": done,
                    "manual": not item.auto})
    return out


def progress(org, request=None) -> dict:
    items = items_for(org, request)
    done = sum(1 for i in items if i["done"])
    return {"items": items, "done": done, "total": len(items), "complete": bool(items) and done == len(items),
            "percent": round(done * 100 / len(items)) if items else 100}


def tick(key: str) -> None:
    ChecklistProgress.objects.get_or_create(item_key=key)
