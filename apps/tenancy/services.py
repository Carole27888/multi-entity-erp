"""Creating and provisioning organizations, memberships and invitations."""

from __future__ import annotations

from typing import Callable

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from apps.core.audit import audit

from .context import tenant
from .models import RESERVED_SLUGS, Invitation, Membership, Organization

# Other apps add per-organization reference data (chart of accounts, tax rates, leave types…) here.
_PROVISIONERS: list[Callable] = []


def register_provisioner(func: Callable) -> Callable:
    """func(org) — runs inside `with tenant(org)`; must be idempotent (get_or_create, never overwrite edits)."""
    _PROVISIONERS.append(func)
    return func


class SeatLimitError(Exception):
    pass


class InvitationError(Exception):
    pass


def unique_slug(name: str, exclude_pk=None) -> str:
    base = slugify(name)[:44].strip("-") or "org"
    if base in RESERVED_SLUGS or len(base) < 2:
        base = f"{base}-co"
    slug, n = base, 2
    qs = Organization.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists() or slug in RESERVED_SLUGS:
        slug = f"{base}-{n}"
        n += 1
    return slug


def provision_organization(org) -> None:
    """Built-in roles and every registered provisioner. Safe to re-run at any time."""
    from apps.accounts.models import Role
    from apps.accounts.roles import BUILTIN_ROLES

    with tenant(org, activate_timezone=False):
        for t in BUILTIN_ROLES:
            # Built-in roles are not editable, so keeping them in step with the code is safe.
            Role.objects.update_or_create(key=t.key, is_builtin=True, defaults={
                "name": t.name, "description": t.description, "two_factor_required": t.two_factor_required,
                "idle_timeout_minutes": t.idle_timeout_minutes, "session_max_hours": t.session_max_hours,
                "default_scope": t.default_scope, "sort_order": t.sort_order})
        for func in _PROVISIONERS:
            func(org)


def builtin_role(org, key: str):
    from apps.accounts.models import Role

    with tenant(org, activate_timezone=False):
        return Role.objects.get(key=key, is_builtin=True)


@transaction.atomic
def create_organization(owner, name: str, *, country: str = "KE", currency: str = "KES", timezone_name: str = "Africa/Nairobi",
                        brand_colour: str | None = None, slug: str | None = None, request=None, **extra) -> Organization:
    from apps.billing.models import Plan

    org = Organization(name=name.strip(), slug=slug or unique_slug(name), country_id=country, currency=currency,
                       timezone=timezone_name, brand_colour=brand_colour or settings.BRAND_COLOUR, **extra)
    org.plan = Plan.objects.filter(key=settings.TRIAL_PLAN).first()
    org.start_trial()
    org.save()
    provision_organization(org)
    Membership.objects.create(user=owner, organization=org, role=builtin_role(org, "owner"))
    audit("organization_created", request, user=owner, organization=org, target=org.slug)
    return org


# --- Seats ------------------------------------------------------------------------------------------

def seats_used(org) -> int:
    members = Membership.objects.filter(organization=org, status=Membership.Status.ACTIVE).count()
    with tenant(org, activate_timezone=False):
        pending = Invitation.objects.filter(accepted_at__isnull=True, revoked_at__isnull=True,
                                            expires_at__gt=timezone.now()).count()
    return members + pending


def seat_limit(org) -> int | None:
    plan = org.effective_plan
    return plan.max_users if plan else None


def check_seat_available(org, extra: int = 1) -> None:
    limit = seat_limit(org)
    if limit is not None and seats_used(org) + extra > limit:
        raise SeatLimitError(f"Your {org.effective_plan.name} plan includes {limit} users. Upgrade to add more people.")


# --- Invitations ---------------------------------------------------------------------------------------

def invite(org, email: str, role, invited_by, request=None) -> Invitation:
    email = email.strip().lower()
    if Membership.objects.filter(organization=org, user__email__iexact=email).exists():
        raise InvitationError(f"{email} is already a member.")
    with tenant(org, activate_timezone=False):
        existing = Invitation.objects.filter(email__iexact=email, accepted_at__isnull=True, revoked_at__isnull=True,
                                             expires_at__gt=timezone.now()).first()
        if existing:
            existing.role = role
            existing.save(update_fields=["role"])
            send_invitation(existing)
            return existing
        check_seat_available(org)
        inv = Invitation.objects.create(email=email, role=role, invited_by=invited_by)
    send_invitation(inv)
    audit("member_invited", request, organization=org, target=email, role=role.name)
    return inv


def invitation_url(inv) -> str:
    return f"{settings.SITE_URL}/invite/{inv.token}/"


def send_invitation(inv) -> None:
    org = Organization.objects.get(pk=inv.organization_id)
    ctx = {"org": org, "inv": inv, "url": invitation_url(inv), "PRODUCT_NAME": settings.PRODUCT_NAME,
           "inviter": inv.invited_by}
    send_mail(f"{inv.invited_by or org.name} invited you to {org.name}",
              render_to_string("tenancy/email/invitation.txt", ctx), None, [inv.email])


def find_invitation(token: str) -> Invitation | None:
    """Look an invitation up by its token, across organizations (platform code)."""
    inv = Invitation.unscoped.select_related("role").filter(token=token).first()
    return inv if inv and inv.is_open else None


@transaction.atomic
def accept_invitation(inv, user, request=None) -> Membership:
    org = Organization.objects.get(pk=inv.organization_id)
    if user.email.lower() != inv.email.lower():
        raise InvitationError("This invitation was sent to a different email address.")
    membership, created = Membership.objects.get_or_create(
        user=user, organization=org, defaults={"role_id": inv.role_id, "invited_by": inv.invited_by})
    if not created and membership.status != Membership.Status.ACTIVE:
        membership.status = Membership.Status.ACTIVE
        membership.role_id = inv.role_id
        membership.save(update_fields=["status", "role"])
    with tenant(org, activate_timezone=False):
        Invitation.objects.filter(pk=inv.pk).update(accepted_at=timezone.now())
    if not user.email_verified_at:
        user.email_verified_at = timezone.now()  # the link reached their inbox
        user.save(update_fields=["email_verified_at"])
    audit("invitation_accepted", request, user=user, organization=org, target=user.email)
    return membership
