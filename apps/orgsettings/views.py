"""Settings inside an organization: profile and branding, modules, team and invitations, roles, departments."""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts import roles as builtin
from apps.accounts.models import Department, Role, RolePermission
from apps.accounts.permissions import PermSet, has_perm, require_perm, tenant_object
from apps.core import modules
from apps.core.audit import audit
from apps.tenancy import services as tenancy
from apps.tenancy.models import Invitation, Membership

from .forms import DepartmentForm, InviteForm, MembershipForm, ProfileForm, RoleForm


def _is_owner(request) -> bool:
    return request.membership.role.is_builtin and request.membership.role.key == builtin.OWNER


@require_perm("settings.view")
def index(request):
    org = request.organization
    return render(request, "orgsettings/index.html", {
        "page_title": "Settings",
        "seats": tenancy.seats_used(org), "seat_limit": tenancy.seat_limit(org),
        "role_count": Role.objects.count(), "department_count": Department.objects.count(),
    })


@require_perm("settings.view")
def profile(request):
    org = request.organization
    can_edit = has_perm(request, "settings.edit")
    form = ProfileForm(request.POST or None, request.FILES or None, instance=org)
    if request.method == "POST":
        if not can_edit:
            raise Http404
        if form.is_valid():
            form.save()
            audit("organization_profile_updated", request, target=org.slug, fields=form.changed_data)
            messages.success(request, "Profile saved.")
            return redirect("orgsettings:profile")
    return render(request, "orgsettings/profile.html", {"page_title": "Profile & branding", "form": form,
                                                         "can_edit": can_edit})


@require_perm("settings.view")
def modules_view(request):
    org = request.organization
    can_edit = has_perm(request, "settings.edit")
    rows = []
    for entry in modules.CATALOGUE.values():
        if entry.core:
            continue
        mod = modules.get(entry.key)
        rows.append({"entry": entry, "enabled": entry.key in (org.enabled_modules or []),
                     "built": mod is not None, "locked": bool(entry.plan_feature) and not org.has_feature(entry.plan_feature)})
    if request.method == "POST":
        if not can_edit:
            raise Http404
        wanted = set(request.POST.getlist("modules"))
        allowed = {r["entry"].key for r in rows if not r["locked"]}
        keep_locked = {k for k in org.enabled_modules or [] if k not in allowed}
        org.enabled_modules = sorted((wanted & allowed) | keep_locked)
        org.save(update_fields=["enabled_modules", "updated_at"])
        audit("modules_changed", request, modules=org.enabled_modules)
        messages.success(request, "Modules updated.")
        return redirect("orgsettings:modules")
    return render(request, "orgsettings/modules.html", {"page_title": "Modules", "rows": rows, "can_edit": can_edit})


# --- Team -------------------------------------------------------------------------------------------------

@require_perm("settings.manage_team")
def members(request):
    org = request.organization
    form = InviteForm(request.POST or None, can_grant_owner=_is_owner(request))
    if request.method == "POST" and form.is_valid():
        try:
            tenancy.invite(org, form.cleaned_data["email"], form.cleaned_data["role"], request.user, request)
            messages.success(request, f"Invitation sent to {form.cleaned_data['email']}.")
            return redirect("orgsettings:members")
        except tenancy.SeatLimitError as exc:
            form.add_error(None, str(exc))
        except tenancy.InvitationError as exc:
            form.add_error("email", str(exc))
    team = (Membership.objects.filter(organization=org).select_related("user", "role")
            .prefetch_related("departments").order_by("status", "user__full_name"))
    invitations = Invitation.objects.filter(accepted_at__isnull=True, revoked_at__isnull=True).select_related("role")
    return render(request, "orgsettings/members.html", {
        "page_title": "Team", "team": team, "invitations": invitations, "form": form,
        "seats": tenancy.seats_used(org), "seat_limit": tenancy.seat_limit(org),
    })


def _owners_left(org, excluding):
    return (Membership.objects.filter(organization=org, role__key=builtin.OWNER, role__is_builtin=True,
                                      status=Membership.Status.ACTIVE).exclude(pk=excluding.pk).exists())


@tenant_object(Membership)
@require_perm("settings.manage_team")
def member_edit(request, pk):
    org = request.organization
    member = get_object_or_404(Membership.objects.select_related("user", "role"), pk=pk, organization=org)
    is_owner_row = member.role.is_builtin and member.role.key == builtin.OWNER
    if is_owner_row and not _is_owner(request):
        messages.error(request, "Only an owner can change another owner.")
        return redirect("orgsettings:members")
    form = MembershipForm(request.POST or None, instance=member, can_grant_owner=_is_owner(request))
    if request.method == "POST" and form.is_valid():
        changed = form.save(commit=False)
        demoting = is_owner_row and (changed.role.key != builtin.OWNER or changed.status != Membership.Status.ACTIVE)
        if demoting and not _owners_left(org, member):
            form.add_error(None, "Every organization needs at least one active owner.")
        elif member.user_id == request.user.pk and changed.status != Membership.Status.ACTIVE:
            form.add_error("status", "You can't disable your own access.")
        else:
            changed.save()
            form.save_m2m()
            audit("member_changed", request, target=member.user.email, role=changed.role.name, status=changed.status)
            messages.success(request, f"{member.user} updated.")
            return redirect("orgsettings:members")
    return render(request, "orgsettings/member_edit.html", {"page_title": str(member.user), "member": member, "form": form})


@require_POST
@tenant_object(Invitation)
@require_perm("settings.manage_team")
def invitation_revoke(request, pk):
    inv = get_object_or_404(Invitation, pk=pk, accepted_at__isnull=True)
    from django.utils import timezone

    inv.revoked_at = timezone.now()
    inv.save(update_fields=["revoked_at"])
    audit("invitation_revoked", request, target=inv.email)
    messages.success(request, f"Invitation to {inv.email} cancelled.")
    return redirect("orgsettings:members")


@require_POST
@tenant_object(Invitation)
@require_perm("settings.manage_team")
def invitation_resend(request, pk):
    inv = get_object_or_404(Invitation, pk=pk, accepted_at__isnull=True, revoked_at__isnull=True)
    tenancy.send_invitation(inv)
    messages.success(request, f"Invitation sent again to {inv.email}.")
    return redirect("orgsettings:members")


# --- Roles ------------------------------------------------------------------------------------------------

def _matrix(perms: dict[str, str], editable: bool, default_scope: str = "all"):
    rows = []
    for mod in modules.all_modules():
        cells = []
        for action in modules.ACTIONS:
            key = f"{mod.key}.{action}"
            cells.append({"action": action, "key": key, "available": action in mod.actions, "on": key in perms})
        extras = [{"key": f"{mod.key}.{p}", "label": label, "on": f"{mod.key}.{p}" in perms}
                  for p, label in mod.extra_permissions.items()]
        scope = perms.get(f"{mod.key}.view", default_scope)
        rows.append({"module": mod, "cells": cells, "extras": extras, "scope": scope})
    return {"rows": rows, "actions": modules.ACTIONS, "editable": editable, "scopes": Role.Scope.choices}


@require_perm("settings.manage_roles")
def roles(request):
    items = Role.objects.annotate(members=Count("memberships")).order_by("-is_builtin", "sort_order", "name")
    return render(request, "orgsettings/roles.html", {"page_title": "Roles & permissions", "roles": items})


@tenant_object(Role)
@require_perm("settings.manage_roles")
def role_view(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if not role.is_builtin:
        return redirect("orgsettings:role_edit", pk=role.pk)
    perms = builtin.builtin_permissions(role.key)
    return render(request, "orgsettings/role_view.html", {"page_title": role.name, "role": role,
                                                          "matrix": _matrix(perms, editable=False, default_scope=role.default_scope)})


def _save_matrix(request, role):
    valid = {k for k, _ in modules.all_permission_keys()}
    chosen = [k for k in request.POST.getlist("perm") if k in valid]
    scope_for = {}
    for mod in modules.all_modules():
        value = request.POST.get(f"scope_{mod.key}", role.default_scope)
        scope_for[mod.key] = value if value in dict(Role.Scope.choices) else role.default_scope
    RolePermission.objects.filter(role=role).delete()
    RolePermission.objects.bulk_create([
        RolePermission(role=role, permission=k, scope=scope_for.get(k.split(".")[0], role.default_scope),
                       organization=request.organization) for k in sorted(set(chosen))])


def _role_form_page(request, role=None, start_perms=None):
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            _save_matrix(request, saved)
        audit("role_saved", request, target=saved.name)
        messages.success(request, f"Role “{saved.name}” saved.")
        return redirect("orgsettings:roles")
    if role is not None and start_perms is None:
        start_perms = PermSet({p.permission: p.scope for p in role.permissions.all()}).perms
    return render(request, "orgsettings/role_edit.html", {
        "page_title": role.name if role else "New role", "role": role, "form": form,
        "matrix": _matrix(start_perms or {}, editable=True, default_scope=role.default_scope if role else "all"),
    })


@require_perm("settings.manage_roles")
def role_new(request):
    source = request.GET.get("from")
    start = {}
    initial_role = None
    if source:
        src = get_object_or_404(Role, pk=source)
        start = (builtin.builtin_permissions(src.key) if src.is_builtin
                 else {p.permission: p.scope for p in src.permissions.all()})
        initial_role = Role(name=f"{src.name} (custom)", description=src.description, default_scope=src.default_scope,
                            two_factor_required=src.two_factor_required, idle_timeout_minutes=src.idle_timeout_minutes,
                            session_max_hours=src.session_max_hours)
    if request.method == "GET" and initial_role is not None:
        form = RoleForm(instance=initial_role)
        return render(request, "orgsettings/role_edit.html", {"page_title": "New role", "role": None, "form": form,
                                                               "matrix": _matrix(start, editable=True,
                                                                                 default_scope=initial_role.default_scope)})
    return _role_form_page(request, None, start)


@tenant_object(Role)
@require_perm("settings.manage_roles")
def role_edit(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if role.is_builtin:
        return redirect("orgsettings:role_view", pk=role.pk)
    return _role_form_page(request, role)


@require_POST
@tenant_object(Role)
@require_perm("settings.manage_roles")
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk, is_builtin=False)
    if role.memberships.exists():
        messages.error(request, "Move everyone off this role before deleting it.")
        return redirect("orgsettings:role_edit", pk=role.pk)
    name = role.name
    role.delete()
    audit("role_deleted", request, target=name)
    messages.success(request, f"Role “{name}” deleted.")
    return redirect("orgsettings:roles")


# --- Departments --------------------------------------------------------------------------------------------

@require_perm("settings.manage_team")
def departments(request):
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Department added.")
        return redirect("orgsettings:departments")
    items = Department.objects.annotate(people=Count("members")).order_by("name")
    return render(request, "orgsettings/departments.html", {"page_title": "Departments", "items": items, "form": form})


@require_POST
@tenant_object(Department)
@require_perm("settings.manage_team")
def department_delete(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    dept.delete()
    messages.success(request, f"Department “{dept.name}” deleted.")
    return redirect("orgsettings:departments")
