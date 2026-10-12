"""The current organization for this request, job or command (a context variable, so it is per thread/task).

Requests: set by apps.tenancy.middleware.TenantMiddleware.
Jobs: set by the job runner from Job.organization.
Commands, seeders, tests and shell work:

    from apps.tenancy.context import tenant

    with tenant(org):
        Contact.objects.all()   # only org's rows
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

from django.utils import timezone

_current = ContextVar("current_organization", default=None)


class NoTenantError(RuntimeError):
    """A tenant-scoped query or save ran with no current organization."""


class CrossTenantError(RuntimeError):
    """Code tried to save a row that belongs to another organization than the current one."""


def get_current_organization():
    return _current.get()


def current_organization_id() -> int | None:
    org = _current.get()
    return org.pk if org is not None else None


def require_organization():
    org = _current.get()
    if org is None:
        raise NoTenantError("No current organization. Wrap the code in `with tenant(org):`.")
    return org


def set_current_organization(org):
    """Returns a token for reset_current_organization()."""
    return _current.set(org)


def reset_current_organization(token) -> None:
    _current.reset(token)


@contextmanager
def tenant(org, activate_timezone: bool = True):
    """Run a block as `org`: scoped queries, and the organization's time zone for local dates."""
    token = _current.set(org)
    tz_set = False
    if activate_timezone and org is not None and getattr(org, "timezone", ""):
        try:
            timezone.activate(org.timezone)
            tz_set = True
        except Exception:  # noqa: BLE001 - an invalid zone name falls back to settings.TIME_ZONE
            pass
    try:
        yield org
    finally:
        _current.reset(token)
        if tz_set:
            timezone.deactivate()


@contextmanager
def no_tenant():
    """Run a block with no current organization (platform code)."""
    token = _current.set(None)
    try:
        yield
    finally:
        _current.reset(token)
