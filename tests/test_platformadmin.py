"""Platform admin: access, suspend/restore, read-only mode and audited impersonation."""

import pytest

from apps.core.models import AuditLog
from apps.tenancy.models import Membership, Organization
from tests.factories import login, make_user


@pytest.fixture
def platform_user(db):
    return make_user("support@platform.co.ke", full_name="Platform Support", is_platform_staff=True)


@pytest.mark.django_db
def test_only_platform_staff_can_open_it(client, org1, owner1, platform_user):
    login(client, owner1)
    assert client.get("/platform/").status_code == 404
    login(client, platform_user)
    response = client.get("/platform/")
    assert response.status_code == 200 and org1.name.encode() in response.content
    assert client.get(f"/platform/orgs/{org1.pk}/").status_code == 200


@pytest.mark.django_db
def test_platform_staff_are_not_members(client, org1, platform_user):
    login(client, platform_user)
    assert client.get(f"/{org1.slug}/").status_code == 404


@pytest.mark.django_db
def test_suspend_and_restore(client, org1, owner1, platform_user):
    login(client, platform_user)
    assert client.post(f"/platform/orgs/{org1.pk}/suspend/", {"reason": ""}).status_code == 302
    org1.refresh_from_db()
    assert org1.status == "trial"  # a reason is required
    client.post(f"/platform/orgs/{org1.pk}/suspend/", {"reason": "Unpaid for 60 days"})
    org1.refresh_from_db()
    assert org1.status == "suspended"
    assert AuditLog.objects.filter(action="organization_suspended", organization=org1).exists()
    login(client, owner1)
    assert client.get(f"/{org1.slug}/").status_code == 403
    assert client.get(f"/s/{org1.slug}/").status_code == 404
    login(client, platform_user)
    client.post(f"/platform/orgs/{org1.pk}/restore/")
    org1.refresh_from_db()
    assert org1.status == "trial"
    login(client, owner1)
    assert client.get(f"/{org1.slug}/").status_code == 200


@pytest.mark.django_db
def test_read_only_org_can_view_but_not_change(client, org1, owner1):
    Organization.objects.filter(pk=org1.pk).update(status="read_only")
    login(client, owner1)
    page = client.get(f"/{org1.slug}/settings/profile/")
    assert page.status_code == 200 and b"Read-only" in page.content
    response = client.post(f"/{org1.slug}/settings/profile/", {"name": "Changed"})
    assert response.status_code == 402
    org1.refresh_from_db()
    assert org1.name != "Changed"


@pytest.mark.django_db
def test_impersonation_is_audited_bannered_and_limited(client, org1, owner1, platform_user):
    login(client, platform_user)
    membership = Membership.objects.get(organization=org1, user=owner1)
    response = client.post(f"/platform/orgs/{org1.pk}/impersonate/{membership.pk}/")
    assert response["Location"] == f"/{org1.slug}/"
    page = client.get(f"/{org1.slug}/")
    assert page.status_code == 200
    assert b"You are viewing as" in page.content and platform_user.full_name.encode() in page.content
    log = AuditLog.objects.get(action="impersonation_started")
    assert log.user == platform_user and log.organization == org1 and log.target == owner1.email
    # Sensitive account changes are blocked while impersonating.
    assert client.get("/accounts/password/change/")["Location"] == "/accounts/security/"
    # Platform pages are closed while viewing as someone else.
    assert client.get("/platform/").status_code == 404
    # Audit entries made while impersonating name the platform user as well.
    client.post(f"/{org1.slug}/settings/modules/", {"modules": ["crm"]})
    entry = AuditLog.objects.get(action="modules_changed")
    assert entry.user == owner1 and entry.impersonator == platform_user
    stop = client.post("/platform/impersonation/stop/")
    assert stop["Location"] == f"/platform/orgs/{org1.pk}/"
    assert client.get("/platform/").status_code == 200
    assert AuditLog.objects.filter(action="impersonation_stopped", user=platform_user).exists()
    assert int(client.session["_auth_user_id"]) == platform_user.pk


@pytest.mark.django_db
def test_platform_staff_cannot_be_impersonated(client, org1, platform_user):
    other_staff = make_user(is_platform_staff=True)
    from apps.tenancy.services import builtin_role

    m = Membership.objects.create(user=other_staff, organization=org1, role=builtin_role(org1, "staff"))
    login(client, platform_user)
    client.post(f"/platform/orgs/{org1.pk}/impersonate/{m.pk}/")
    assert int(client.session["_auth_user_id"]) == platform_user.pk
