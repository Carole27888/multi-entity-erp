"""Tiny test factories (no extra dependency)."""

import itertools

from django.utils import timezone

from apps.accounts.models import User
from apps.industries.services import apply_pack
from apps.tenancy.models import Membership
from apps.tenancy.services import builtin_role, create_organization

_counter = itertools.count(1)


def make_user(email=None, full_name="Test User", password="pass12345!", **extra):
    extra.setdefault("email_verified_at", timezone.now())
    return User.objects.create_user(email=email or f"user{next(_counter)}@test.co.ke", password=password,
                                    full_name=full_name, **extra)


def make_org(name="Test Org", owner=None, pack="generic", sub_niche="", slug=None, **extra):
    owner = owner or make_user(full_name=f"{name} Owner")
    org = create_organization(owner, name, slug=slug, **extra)
    apply_pack(org, pack, sub_niche)
    org.refresh_from_db()
    org.onboarding_completed_at = timezone.now()
    org.save(update_fields=["onboarding_completed_at"])
    return org


def add_member(org, user=None, role="staff", **extra):
    user = user or make_user()
    Membership.objects.create(user=user, organization=org, role=builtin_role(org, role), **extra)
    return user


def login(client, user):
    """Signed-in session that already passed two-factor (tests switch enforcement on where needed)."""
    client.force_login(user)
    session = client.session
    session["otp_ok"] = True
    session.save()
    return client
