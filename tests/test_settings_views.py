"""Organization settings: profile and branding, modules, team and invitations."""

import pytest
from django.core import mail

from apps.accounts.models import Department, Role
from apps.tenancy.context import tenant
from apps.tenancy.models import Invitation, Membership
from tests.factories import add_member, login, make_user


@pytest.mark.django_db
def test_profile_and_brand_colour(client, org1, owner1):
    login(client, owner1)
    response = client.post(f"/{org1.slug}/settings/profile/", {
        "name": "Savannah Trails", "legal_name": "Savannah Trails Ltd", "email": "hello@savannah.co.ke",
        "phone": "+254700111222", "address": "Nairobi", "kra_pin": "P051234567X", "website_url": "savannah.co.ke",
        "country": "KE", "currency": "KES", "timezone": "Africa/Nairobi", "brand_colour": "#ffd60a"})
    assert response.status_code == 302
    org1.refresh_from_db()
    assert org1.name == "Savannah Trails" and org1.brand_colour == "#FFD60A"
    assert org1.website_url == "https://savannah.co.ke"
    page = client.get(f"/{org1.slug}/").content.decode()
    # A very light brand colour still gives readable button text: the primary shade is darkened.
    assert "--c-brand:#FFD60A" in page
    assert "--c-primary:#FFD60A" not in page


@pytest.mark.django_db
def test_modules_toggle_respects_plan(client, org1, owner1):
    from apps.billing.models import Plan

    login(client, owner1)
    client.post(f"/{org1.slug}/settings/modules/", {"modules": ["crm", "hr", "api"]})
    org1.refresh_from_db()
    assert "hr" in org1.enabled_modules and "tourism" not in org1.enabled_modules
    assert "api" not in org1.enabled_modules  # needs the Business plan; the trial has Growth features
    org1.status, org1.plan = "active", Plan.objects.get(key="business")
    org1.save()
    client.post(f"/{org1.slug}/settings/modules/", {"modules": ["crm", "api"]})
    org1.refresh_from_db()
    assert "api" in org1.enabled_modules


@pytest.mark.django_db
def test_invite_and_seat_limit(client, org1, owner1):
    from apps.billing.models import Plan

    login(client, owner1)
    with tenant(org1):
        staff = Role.objects.get(key="staff")
    client.post(f"/{org1.slug}/settings/team/", {"email": "guide@savannah.co.ke", "role": staff.pk})
    assert Invitation.unscoped.filter(organization=org1, email="guide@savannah.co.ke").exists()
    assert "invited you" in mail.outbox[-1].subject
    Plan.objects.filter(key="growth").update(max_users=2)
    response = client.post(f"/{org1.slug}/settings/team/", {"email": "two@savannah.co.ke", "role": staff.pk})
    assert b"includes 2 users" in response.content


@pytest.mark.django_db
def test_admin_cannot_grant_owner_and_last_owner_is_protected(client, org1, owner1):
    admin = add_member(org1, make_user(), role="admin")
    login(client, admin)
    with tenant(org1):
        owner_role = Role.objects.get(key="owner")
    page = client.get(f"/{org1.slug}/settings/team/")
    assert f'value="{owner_role.pk}"'.encode() not in page.content
    owner_m = Membership.objects.get(organization=org1, user=owner1)
    assert client.get(f"/{org1.slug}/settings/team/{owner_m.pk}/").status_code == 302  # owners only
    login(client, owner1)
    response = client.post(f"/{org1.slug}/settings/team/{owner_m.pk}/", {"role": owner_role.pk, "status": "disabled"})
    assert b"at least one active owner" in response.content or b"disable your own" in response.content
    owner_m.refresh_from_db()
    assert owner_m.status == "active"


@pytest.mark.django_db
def test_member_departments_and_role_change(client, org1, owner1, staff1):
    login(client, owner1)
    with tenant(org1):
        dept = Department.objects.create(name="Operations")
        ops = Role.objects.get(key="operations")
    m = Membership.objects.get(organization=org1, user=staff1)
    client.post(f"/{org1.slug}/settings/team/{m.pk}/", {"role": ops.pk, "title": "Guide", "departments": [dept.pk],
                                                         "status": "active"})
    m.refresh_from_db()
    with tenant(org1):
        assert m.role == ops and m.title == "Guide" and list(m.departments.all()) == [dept]


@pytest.mark.django_db
def test_revoke_invitation(client, org1, owner1):
    from apps.tenancy.services import builtin_role, invite

    inv = invite(org1, "late@test.co.ke", builtin_role(org1, "staff"), owner1)
    login(client, owner1)
    client.post(f"/{org1.slug}/settings/invitations/{inv.pk}/revoke/")
    inv = Invitation.unscoped.get(pk=inv.pk)
    assert inv.revoked_at is not None
    assert client.get(f"/invite/{inv.token}/").status_code == 404


@pytest.mark.django_db
def test_checklist_ticks_and_hides(client, org1, owner1):
    login(client, owner1)
    page = client.get(f"/{org1.slug}/")
    assert b"Getting started" in page.content
    client.post(f"/{org1.slug}/checklist/dismiss/")
    assert b"Getting started" not in client.get(f"/{org1.slug}/").content
