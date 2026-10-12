"""One permission check for views, templates, the API and tests: has_perm(request, "crm.edit").

Permissions are "<module>.<action>" (actions: view, create, edit, delete, approve, export) plus a module's extra
confidential permissions such as "hr.view_salary" or "tourism.view_margin". Each carries a record scope
(all / department / own) applied by scope_queryset().
"""

from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404

from . import roles


class _ModulePerms:
    def __init__(self, permset, module):
        self._p, self._m = permset, module

    def __getitem__(self, action):
        return self._p.has(f"{self._m}.{action}")

    def __bool__(self):
        return self._p.has(f"{self._m}.view")


class PermSet:
    """The permissions of one membership. In templates: {% if can.crm.edit %} … {% endif %}."""

    def __init__(self, perms: dict[str, str] | None = None, membership=None):
        self.perms = perms or {}
        self.membership = membership

    @classmethod
    def for_membership(cls, membership) -> "PermSet":
        role = membership.role
        if role.is_builtin:
            perms = roles.builtin_permissions(role.key)
        else:
            from .models import RolePermission

            perms = dict(RolePermission.objects.filter(role_id=role.pk).values_list("permission", "scope"))
            perms.setdefault("dashboard.view", role.default_scope)
        return cls(perms, membership)

    def has(self, key: str) -> bool:
        return key in self.perms

    def scope(self, key: str) -> str | None:
        return self.perms.get(key)

    def __getitem__(self, module):
        return _ModulePerms(self, module)

    def __contains__(self, key):
        return self.has(key)


EMPTY = PermSet()


def perms_for(request) -> PermSet:
    return getattr(request, "perms", None) or EMPTY


def has_perm(request, key: str) -> bool:
    return perms_for(request).has(key)


def check_perm(request, key: str) -> None:
    if not has_perm(request, key):
        raise PermissionDenied(f"Missing permission {key}")


def require_perm(*keys: str, module: str | None = None):
    """View decorator: the module must be enabled for the organization and the user must hold every key."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            org = getattr(request, "organization", None)
            mod = module or (keys[0].split(".")[0] if keys else None)
            if org is None or getattr(request, "membership", None) is None:
                raise Http404
            if mod and not org.is_module_enabled(mod):
                raise Http404("Module not enabled")
            for key in keys:
                check_perm(request, key)
            return view(request, *args, **kwargs)

        wrapped.required_perms = keys
        return wrapped

    return decorator


def scope_queryset(qs, request, key: str, owner_field: str = "owner", department_field: str | None = None):
    """Limit qs to the records the user may see under `key` (e.g. "crm.view").

    all → everything in the organization; department → records owned by members of the user's departments
    (or whose department_field is one of them); own → only records owned by the user.
    """
    scope = perms_for(request).scope(key)
    if scope is None:
        return qs.none()
    if scope == "all":
        return qs
    user = request.user
    if scope == "department":
        membership = request.membership
        dept_ids = list(membership.departments.values_list("pk", flat=True))
        if not dept_ids:
            return qs.filter(**{owner_field: user})
        from apps.tenancy.models import Membership

        member_ids = (Membership.objects.filter(organization=request.organization, departments__in=dept_ids)
                      .values_list("user_id", flat=True))
        cond = Q(**{f"{owner_field}__in": member_ids}) | Q(**{owner_field: user})
        if department_field:
            cond |= Q(**{f"{department_field}__in": dept_ids})
        return qs.filter(cond).distinct()
    return qs.filter(**{owner_field: user})


def tenant_object(model, kwarg: str = "pk"):
    """Marks a view whose URL kwarg identifies a row of `model`. The tenant-isolation test reads this to request
    the view with ANOTHER organization's row and expect a 404."""

    def decorator(view):
        targets = dict(getattr(view, "tenant_objects", {}))
        targets[kwarg] = model
        view.tenant_objects = targets
        return view

    return decorator
