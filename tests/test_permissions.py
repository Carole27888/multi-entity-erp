"""Built-in roles, custom roles from the permission matrix, record scope and view protection."""

import pytest

from apps.accounts import roles
from apps.accounts.models import Department, Role, RolePermission
from apps.accounts.permissions import PermSet, scope_queryset
from apps.core.models import Attachment
from apps.tenancy.context import tenant
from apps.tenancy.models import Membership
from tests.factories import add_member, login, make_user


def perms_of(org, user):
    with tenant(org):
        return PermSet.for_membership(Membership.objects.select_related("role").get(organization=org, user=user))


@pytest.mark.django_db
def test_builtin_roles_are_provisioned_for_every_organization(org1, org2):
    for org in (org1, org2):
        with tenant(org):
            keys = set(Role.objects.filter(is_builtin=True).values_list("key", flat=True))
        assert keys == {r.key for r in roles.BUILTIN_ROLES}


@pytest.mark.django_db
def test_owner_has_everything_including_confidential(org1, owner1):
    p = perms_of(org1, owner1)
    assert p.has("settings.manage_roles") and p.has("settings.edit") and p.has("dashboard.view")


@pytest.mark.django_db
@pytest.mark.parametrize("role,can_settings,can_team", [
    ("admin", True, True), ("manager", False, False), ("finance", False, False), ("sales", False, False),
    ("operations", False, False), ("staff", False, False), ("read_only", False, False)])
def test_builtin_role_settings_access(org1, role, can_settings, can_team):
    user = add_member(org1, make_user(), role=role)
    p = perms_of(org1, user)
    assert p.has("dashboard.view")
    assert p.has("settings.edit") is can_settings
    assert p.has("settings.manage_team") is can_team


@pytest.mark.django_db
def test_read_only_can_view_settings_but_not_change(client, org1):
    user = add_member(org1, make_user(), role="read_only")
    login(client, user)
    assert client.get(f"/{org1.slug}/settings/profile/").status_code == 200
    assert client.post(f"/{org1.slug}/settings/profile/", {"name": "Changed"}).status_code == 404
    org1.refresh_from_db()
    assert org1.name != "Changed"


@pytest.mark.django_db
def test_staff_cannot_open_team_or_roles(client, org1, staff1):
    login(client, staff1)
    assert client.get(f"/{org1.slug}/settings/team/").status_code == 403
    assert client.get(f"/{org1.slug}/settings/roles/").status_code == 403
    # ...and the menu doesn't offer them.
    html = client.get(f"/{org1.slug}/settings/").content.decode()
    assert "/settings/team/" not in html and "/settings/roles/" not in html


@pytest.mark.django_db
def test_custom_role_from_the_matrix(client, org1, owner1):
    login(client, owner1)
    response = client.post(f"/{org1.slug}/settings/roles/new/", {
        "name": "Front desk", "description": "Reception", "default_scope": "own", "idle_timeout_minutes": 30,
        "session_max_hours": 12, "two_factor_required": "on",
        "perm": ["dashboard.view", "settings.view", "settings.manage_team", "nonsense.view"],
        "scope_settings": "department"})
    assert response.status_code == 302
    with tenant(org1):
        role = Role.objects.get(name="Front desk")
        perms = dict(RolePermission.objects.filter(role=role).values_list("permission", "scope"))
    assert perms == {"dashboard.view": "own", "settings.view": "department", "settings.manage_team": "department"}
    assert role.two_factor_required and role.idle_timeout_minutes == 30
    user = add_member(org1, make_user(), role="staff")
    Membership.objects.filter(user=user).update(role=role)
    p = perms_of(org1, user)
    assert p.has("settings.manage_team") and not p.has("settings.edit")
    assert user.two_factor_required is False  # TWO_FACTOR_ENFORCED is off in tests
    login(client, user)
    assert client.get(f"/{org1.slug}/settings/team/").status_code == 200
    assert client.get(f"/{org1.slug}/settings/profile/").status_code == 200
    assert client.get(f"/{org1.slug}/settings/roles/").status_code == 403


@pytest.mark.django_db
def test_custom_role_requiring_two_factor_applies_when_enforced(org1, settings):
    settings.TWO_FACTOR_ENFORCED = True
    with tenant(org1):
        role = Role.objects.create(name="Cashier", two_factor_required=True)
    user = add_member(org1, make_user(), role="staff")
    Membership.objects.filter(user=user).update(role=role)
    user = type(user).objects.get(pk=user.pk)
    assert user.two_factor_required


@pytest.mark.django_db
def test_builtin_roles_cannot_be_edited_and_used_roles_cannot_be_deleted(client, org1, owner1):
    login(client, owner1)
    with tenant(org1):
        owner_role = Role.objects.get(key="owner")
        custom = Role.objects.create(name="Temp")
    assert client.get(f"/{org1.slug}/settings/roles/{owner_role.pk}/edit/")["Location"].endswith(f"/roles/{owner_role.pk}/")
    assert client.post(f"/{org1.slug}/settings/roles/{owner_role.pk}/delete/").status_code == 404
    user = add_member(org1, make_user(), role="staff")
    Membership.objects.filter(user=user).update(role=custom)
    client.post(f"/{org1.slug}/settings/roles/{custom.pk}/delete/")
    with tenant(org1):
        assert Role.objects.filter(pk=custom.pk).exists()


@pytest.mark.django_db
def test_record_scope_own_department_all(org1, owner1, rf):
    a = add_member(org1, make_user(full_name="A"), role="sales")
    b = add_member(org1, make_user(full_name="B"), role="sales")
    mgr = add_member(org1, make_user(full_name="M"), role="manager")
    with tenant(org1):
        dept = Department.objects.create(name="Sales")
        for u in (a, mgr):
            Membership.objects.get(user=u, organization=org1).departments.add(dept)
        rows = {}
        for u in (a, b, mgr):
            att = Attachment.objects.create(name=f"{u.full_name}.txt", file="x.txt", created_by=u)
            rows[u.full_name] = att.pk

        def visible(user):
            request = rf.get("/")
            request.user, request.organization = user, org1
            request.membership = Membership.objects.select_related("role").get(user=user, organization=org1)
            request.perms = PermSet.for_membership(request.membership)
            qs = scope_queryset(Attachment.objects.all(), request, "dashboard.view", owner_field="created_by")
            return set(qs.values_list("name", flat=True))

        assert visible(a) == {"A.txt"}                    # sales: own records
        assert visible(mgr) == {"A.txt", "M.txt"}         # manager: their department
        request = rf.get("/")
        request.user, request.organization = owner1, org1
        request.membership = Membership.objects.select_related("role").get(user=owner1, organization=org1)
        request.perms = PermSet.for_membership(request.membership)
        assert set(scope_queryset(Attachment.objects.all(), request, "dashboard.view", owner_field="created_by")
                   .values_list("name", flat=True)) == {"A.txt", "B.txt", "M.txt"}


@pytest.mark.django_db
def test_disabled_member_loses_access(client, org1, staff1):
    Membership.objects.filter(user=staff1).update(status=Membership.Status.DISABLED)
    login(client, staff1)
    assert client.get(f"/{org1.slug}/").status_code == 404
