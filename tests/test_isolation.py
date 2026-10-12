"""Tenant isolation: a user of organization 1 can never read, list, change or download anything of organization 2.

The URL walk covers every staff URL in config.urls_tenant automatically. A URL that takes an object id must
declare its model with @tenant_object (or be listed in EXEMPT with a reason), otherwise this test fails — so a
new view can't be added without isolation coverage.
"""

import re
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.accounts.models import Department, Role, RolePermission
from apps.core.models import Attachment, Sequence
from apps.tenancy.base import TenantModel
from apps.tenancy.context import CrossTenantError, NoTenantError, tenant
from apps.tenancy.models import Invitation, Membership
from tests.factories import add_member, login, make_user

MARKER = "ORG2SECRET"

# Models that are deliberately not tenant-scoped, and why.
GLOBAL_MODELS = {
    "accounts.User": "one person can belong to several organizations",
    "tenancy.Organization": "the tenant itself",
    "tenancy.Domain": "looked up by host name before the organization is known",
    "tenancy.Membership": "links a global user to an organization; always filtered by organization",
    "core.Currency": "global reference data",
    "core.Country": "global reference data (country templates)",
    "core.AuditLog": "holds platform events too; tenant code reads it through AuditLog.for_org",
    "core.Job": "the runner reads every organization's jobs; each job runs inside its organization",
    "core.ScheduleState": "job runner bookkeeping",
    "core.JobLock": "job runner bookkeeping",
    "core.JobRunnerHeartbeat": "job runner bookkeeping",
    "billing.Plan": "the platform's own plans",
    "integrations.OutboundMessage": "platform messages (sign-up codes) as well as tenant ones (organization filled in)",
    "onboarding.OnboardingSession": "exists before the organization is created; always read through its user",
}

# Tenant URLs whose kwargs are not object ids.
EXEMPT = {
    "core:checklist_tick": "kwarg is a checklist item key; ticking only writes to the current organization",
}

# Where `.unscoped` may appear (platform code).
UNSCOPED_ALLOWED = ("apps/tenancy/", "apps/platformadmin/", "apps/billing/", "apps/core/jobs/", "apps/core/admin_tools.py")


def _walk(patterns, prefix="", namespace=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            ns = f"{namespace}:{p.namespace}" if namespace and p.namespace else (p.namespace or namespace)
            yield from _walk(p.url_patterns, prefix + str(p.pattern), ns)
        elif isinstance(p, URLPattern):
            name = f"{namespace}:{p.name}" if namespace else p.name
            yield prefix + str(p.pattern), name, p.callback


def tenant_urls():
    return list(_walk(get_resolver(settings.TENANT_URLCONF).url_patterns))


def kwarg_names(route: str) -> list[str]:
    return re.findall(r"<(?:\w+:)?(\w+)>", route)


def org_url(org, name, **kwargs):
    return f"/{org.slug}" + reverse(name, urlconf=settings.TENANT_URLCONF, kwargs=kwargs or None)


@pytest.fixture
def seeded(org1, org2, owner1, owner2):
    """org2 gets one row of every model its URLs expose, each carrying the marker."""
    with tenant(org2):
        role = Role.objects.create(name=f"{MARKER} Role", description=MARKER)
        RolePermission.objects.create(role=role, permission="crm.view")
        dept = Department.objects.create(name=f"{MARKER} Dept")
        Invitation.objects.create(email="org2secret-invite@test.co.ke", role=role, invited_by=owner2)
        att = Attachment(name=f"{MARKER}.txt", permission="dashboard.view")
        att.file.save("secret.txt", ContentFile(MARKER.encode()), save=False)
        att.save()
    member2 = add_member(org2, make_user(full_name=f"{MARKER} Person", email="org2secret@test.co.ke"), role="sales")
    member2_m = Membership.objects.get(user=member2, organization=org2)
    member2_m.departments.add(dept)
    with tenant(org1):
        att1 = Attachment(name="ours.txt", permission="dashboard.view")
        att1.file.save("ours.txt", ContentFile(b"ours"), save=False)
        att1.save()
        Department.objects.create(name="Org1 Dept")
        Role.objects.create(name="Org1 Custom")
        Invitation.objects.create(email="invitee1@test.co.ke", role=Role.objects.get(key="staff"), invited_by=owner1)
    return {"org1": org1, "org2": org2}


def _row_of(model, org):
    manager = model.unscoped if issubclass(model, TenantModel) else model._default_manager
    return manager.filter(organization=org).order_by("-pk").first()


def _snapshot(org):
    out = {}
    for model in (Role, RolePermission, Department, Invitation, Attachment):
        rows = model.unscoped.filter(organization=org)
        out[model.__name__] = sorted((r.pk, str(r)) for r in rows)
    out["Invitation_state"] = sorted(Invitation.unscoped.filter(organization=org).values_list("pk", "revoked_at"))
    out["Membership"] = sorted(Membership.objects.filter(organization=org).values_list("pk", "role_id", "status"))
    return out


# --- Static guarantees ----------------------------------------------------------------------------------------

def test_every_business_model_is_tenant_scoped():
    missing = []
    for model in apps.get_models():
        if not model.__module__.startswith("apps.") or model.__name__.startswith("Historical"):
            continue
        label = f"{model._meta.app_label}.{model.__name__}"
        if issubclass(model, TenantModel):
            continue
        if label not in GLOBAL_MODELS:
            missing.append(label)
    assert not missing, f"Models without an organization (inherit TenantModel or justify in GLOBAL_MODELS): {missing}"


def test_unscoped_manager_only_in_platform_code():
    root = Path(settings.BASE_DIR)
    offenders = []
    for path in (root / "apps").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/migrations/" in rel or rel.startswith(UNSCOPED_ALLOWED):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if ".unscoped" in line:
                offenders.append(f"{rel}:{n}")
    assert not offenders, f".unscoped used outside platform code: {offenders}"


@pytest.mark.django_db
def test_scoped_query_without_organization_fails_closed(org1):
    with pytest.raises(NoTenantError):
        list(Role.objects.all())
    with pytest.raises(NoTenantError):
        Role.objects.count()
    with pytest.raises(NoTenantError):
        Department.objects.create(name="No org")


@pytest.mark.django_db
def test_queryset_built_early_is_scoped_when_it_runs(org1, org2):
    early = Role.objects.filter(is_builtin=True)  # built outside any organization (like a form field at import time)
    with tenant(org1):
        assert {r.organization_id for r in early.all()} == {org1.pk}
    with tenant(org2):
        assert {r.organization_id for r in early.all()} == {org2.pk}


@pytest.mark.django_db
def test_saving_another_organizations_row_is_refused(org1, org2):
    with tenant(org2):
        dept = Department.objects.create(name="Theirs")
    with tenant(org1):
        dept.name = "Hijacked"
        with pytest.raises(CrossTenantError):
            dept.save()
        assert not Department.objects.filter(pk=dept.pk).exists()
        with pytest.raises(Department.DoesNotExist):
            Department.objects.get(pk=dept.pk)


@pytest.mark.django_db
def test_sequences_are_per_organization(org1, org2):
    with tenant(org1):
        assert Sequence.next("invoice", "INV") == "INV-0001"
        assert Sequence.next("invoice", "INV") == "INV-0002"
    with tenant(org2):
        assert Sequence.next("invoice", "INV") == "INV-0001"


def test_every_tenant_url_with_an_id_declares_its_model():
    undeclared = []
    for route, name, callback in tenant_urls():
        kwargs = kwarg_names(route)
        if not kwargs or name in EXEMPT:
            continue
        declared = getattr(callback, "tenant_objects", {})
        if set(kwargs) - set(declared):
            undeclared.append(f"{name} ({route})")
    assert not undeclared, f"Add @tenant_object(Model) to these views (or EXEMPT with a reason): {undeclared}"


# --- The URL walk ------------------------------------------------------------------------------------------------

@pytest.mark.django_db
def test_lists_never_show_another_organizations_data(client, seeded, owner1):
    login(client, owner1)
    org1 = seeded["org1"]
    checked = 0
    for route, name, callback in tenant_urls():
        if kwarg_names(route):
            continue
        response = client.get(org_url(org1, name))
        assert response.status_code in (200, 302, 405), f"{name}: {response.status_code}"
        assert MARKER.encode() not in response.content, f"{name} shows organization 2's data"
        checked += 1
    assert checked >= 8


@pytest.mark.django_db
def test_object_urls_404_for_another_organizations_rows(client, seeded, owner1):
    login(client, owner1)
    org1, org2 = seeded["org1"], seeded["org2"]
    before = _snapshot(org2)
    checked = 0
    for route, name, callback in tenant_urls():
        kwargs = kwarg_names(route)
        if not kwargs or name in EXEMPT:
            continue
        targets = callback.tenant_objects
        theirs = {}
        ours = {}
        for kw in kwargs:
            model = targets[kw]
            row2, row1 = _row_of(model, org2), _row_of(model, org1)
            assert row2 is not None, f"seed organization 2 with a {model.__name__} for {name}"
            theirs[kw], ours[kw] = row2.pk, getattr(row1, "pk", None)
        url = org_url(org1, name, **theirs)
        get = client.get(url)
        assert get.status_code in (404, 405), f"GET {name} with org 2's id answered {get.status_code}"
        assert MARKER.encode() not in get.content
        post = client.post(url, {"name": "Hacked", "email": "x@test.co.ke", "status": "disabled"})
        assert post.status_code in (404, 405), f"POST {name} with org 2's id answered {post.status_code}"
        # Positive control: the same view works for organization 1's own row (so the 404 above means something).
        if all(ours.values()):
            own = client.get(org_url(org1, name, **ours))
            assert own.status_code in (200, 302, 405), f"{name} fails for organization 1's own row: {own.status_code}"
        checked += 1
    assert checked >= 6
    assert _snapshot(org2) == before, "organization 2's data changed"


@pytest.mark.django_db
def test_non_member_gets_404_for_every_page_of_another_organization(client, seeded, owner1):
    login(client, owner1)
    org2 = seeded["org2"]
    for route, name, callback in tenant_urls():
        if kwarg_names(route):
            continue
        response = client.get(org_url(org2, name))
        assert response.status_code == 404, f"{name} of organization 2 answered {response.status_code}"
        assert MARKER.encode() not in response.content


@pytest.mark.django_db
def test_files_of_another_organization_cannot_be_downloaded(client, seeded, owner1):
    login(client, owner1)
    org1, org2 = seeded["org1"], seeded["org2"]
    theirs = Attachment.unscoped.get(organization=org2)
    ours = Attachment.unscoped.get(organization=org1)
    assert client.get(org_url(org1, "core:attachment", pk=theirs.pk)).status_code == 404
    assert client.get(org_url(org2, "core:attachment", pk=theirs.pk)).status_code == 404
    response = client.get(org_url(org1, "core:attachment", pk=ours.pk))
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"ours"
    assert "private" in response["Cache-Control"] and "no-store" in response["Cache-Control"]
    # Files live under the organization's own folder and have no public URL.
    assert theirs.file.name.startswith(f"{org2.pk}/attachments/")
    assert client.get(f"/media/{theirs.file.name}").status_code == 404
    assert client.get(f"{settings.MEDIA_URL}{theirs.file.name}").status_code == 404


@pytest.mark.django_db
def test_attachment_permission_is_checked(client, seeded, org1):
    staff = add_member(org1, make_user(), role="staff")
    login(client, staff)
    with tenant(org1):
        secret = Attachment(name="pay.txt", permission="hr.view_salary", confidential=True)
        secret.file.save("pay.txt", ContentFile(b"pay"), save=False)
        secret.save()
    assert client.get(org_url(org1, "core:attachment", pk=secret.pk)).status_code == 404


@pytest.mark.django_db
def test_onboarding_session_of_another_user_is_404(client, org1, owner1):
    from apps.onboarding.models import OnboardingSession

    other = make_user()
    session = OnboardingSession.objects.create(user=other)
    login(client, owner1)
    assert client.get(f"/onboarding/{session.pk}/business/").status_code == 404
    assert client.post(f"/onboarding/{session.pk}/cancel/").status_code == 404


@pytest.mark.django_db
def test_role_choices_only_offer_own_organization(client, seeded, owner1):
    """A forged role id from organization 2 is rejected by the invite form."""
    login(client, owner1)
    org1, org2 = seeded["org1"], seeded["org2"]
    their_role = Role.unscoped.get(organization=org2, name=f"{MARKER} Role")
    response = client.post(org_url(org1, "orgsettings:members"), {"email": "new@test.co.ke", "role": their_role.pk})
    assert response.status_code == 200  # form re-shown with an error
    assert not Invitation.unscoped.filter(email="new@test.co.ke").exists()
