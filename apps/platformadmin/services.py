"""Platform-admin actions on organizations. This is platform code, so it may use unscoped managers."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import login
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.two_factor import VERIFIED
from apps.core.audit import audit
from apps.tenancy.models import Membership, Organization

IMPERSONATOR = "impersonator_id"
IMPERSONATION_ORG = "impersonation_org"
IMPERSONATION_STARTED = "impersonation_started"


class ImpersonationError(Exception):
    pass


def organizations():
    return (Organization.objects.select_related("plan")
            .annotate(members=Count("memberships", filter=Q(memberships__status=Membership.Status.ACTIVE)))
            .order_by("-created_at"))


def usage(org) -> dict:
    from apps.core.models import Attachment, Job

    storage = sum(a.size for a in Attachment.unscoped.filter(organization=org).only("size"))
    return {
        "members": Membership.objects.filter(organization=org, status=Membership.Status.ACTIVE).count(),
        "storage_mb": round(storage / (1024 * 1024), 1),
        "jobs_failed": Job.objects.filter(organization=org, status=Job.Status.FAILED).count(),
        "jobs_queued": Job.objects.filter(organization=org, status=Job.Status.QUEUED).count(),
    }


def suspend(org, reason: str, request) -> None:
    org.status = Organization.Status.SUSPENDED
    org.suspended_reason = reason[:255]
    org.save(update_fields=["status", "suspended_reason", "updated_at"])
    audit("organization_suspended", request, organization=org, target=org.slug, reason=reason)


def restore(org, request) -> None:
    trial_running = bool(org.trial_ends_at and org.trial_ends_at > timezone.now())  # no paid subscription before phase 8
    org.status = Organization.Status.TRIAL if trial_running else Organization.Status.ACTIVE
    org.suspended_reason = ""
    org.save(update_fields=["status", "suspended_reason", "updated_at"])
    audit("organization_restored", request, organization=org, target=org.slug)


def start_impersonation(request, membership) -> None:
    impersonator = request.user
    if request.session.get(IMPERSONATOR):
        raise ImpersonationError("Stop the current impersonation first.")
    target = membership.user
    if target.is_platform_staff or target.pk == impersonator.pk:
        raise ImpersonationError("Platform staff can't be impersonated.")
    org = membership.organization
    audit("impersonation_started", request, user=impersonator, organization=org, target=target.email)
    login(request, target, backend=settings.AUTHENTICATION_BACKENDS[0])  # new session for the target
    request.session[IMPERSONATOR] = impersonator.pk
    request.session[IMPERSONATION_ORG] = org.pk
    request.session[IMPERSONATION_STARTED] = timezone.now().isoformat()
    request.session[VERIFIED] = True
    request.session.set_expiry(60 * 60)  # an impersonation lasts at most an hour


def stop_impersonation(request):
    from apps.accounts.models import User

    pk = request.session.get(IMPERSONATOR)
    if not pk:
        return None
    impersonator = User.objects.filter(pk=pk, is_platform_staff=True, is_active=True).first()
    target = request.user
    org = Organization.objects.filter(pk=request.session.get(IMPERSONATION_ORG)).first()
    if impersonator is None:
        from django.contrib.auth import logout

        logout(request)
        return None
    login(request, impersonator, backend=settings.AUTHENTICATION_BACKENDS[0])
    request.session[VERIFIED] = True
    audit("impersonation_stopped", request, user=impersonator, organization=org, target=getattr(target, "email", ""))
    return org
