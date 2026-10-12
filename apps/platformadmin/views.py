from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import AuditLog, Job, JobRunnerHeartbeat
from apps.core.monitoring import checks, healthy
from apps.tenancy.models import Membership, Organization

from . import services


def platform_staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_platform_staff or request.session.get(services.IMPERSONATOR):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapped


@platform_staff_required
def dashboard(request):
    orgs = services.organizations()
    status_counts = {s: 0 for s, _ in Organization.Status.choices}
    for org in orgs:
        status_counts[org.status] += 1
    q = request.GET.get("q", "").strip()
    if q:
        orgs = orgs.filter(name__icontains=q) | orgs.filter(slug__icontains=q)
    status = request.GET.get("status")
    if status:
        orgs = orgs.filter(status=status)
    results = checks()
    from apps.industries.registry import choices as industry_choices

    return render(request, "platformadmin/dashboard.html", {
        "industry_names": dict(industry_choices()),
        "page_title": "Platform", "orgs": orgs[:200], "status_counts": status_counts, "statuses": Organization.Status.choices,
        "checks": results, "healthy": healthy(results), "last_run": JobRunnerHeartbeat.objects.first(),
        "failed_jobs": Job.objects.filter(status=Job.Status.FAILED).count(), "q": q, "status": status,
    })


@platform_staff_required
def org_detail(request, pk):
    org = get_object_or_404(Organization.objects.select_related("plan"), pk=pk)
    members = Membership.objects.filter(organization=org).select_related("user", "role").order_by("user__full_name")
    log = AuditLog.objects.filter(organization=org).select_related("user", "impersonator")[:50]
    return render(request, "platformadmin/org_detail.html", {
        "page_title": org.name, "o": org, "members": members, "usage": services.usage(org), "log": log,
    })


@require_POST
@platform_staff_required
def org_suspend(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Give a reason for the suspension (it is recorded in the audit log).")
        return redirect("platformadmin:org_detail", pk=pk)
    services.suspend(org, reason, request)
    messages.success(request, f"{org.name} is suspended.")
    return redirect("platformadmin:org_detail", pk=pk)


@require_POST
@platform_staff_required
def org_restore(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    services.restore(org, request)
    messages.success(request, f"{org.name} is restored.")
    return redirect("platformadmin:org_detail", pk=pk)


@require_POST
@platform_staff_required
def impersonate(request, pk, membership_pk):
    membership = get_object_or_404(Membership.objects.select_related("user", "organization"), pk=membership_pk,
                                   organization_id=pk, status=Membership.Status.ACTIVE)
    try:
        services.start_impersonation(request, membership)
    except services.ImpersonationError as exc:
        messages.error(request, str(exc))
        return redirect("platformadmin:org_detail", pk=pk)
    return redirect(membership.organization.app_path)


@require_POST
@login_required
def stop_impersonating(request):
    org = services.stop_impersonation(request)
    if org is None:
        return redirect("accounts:login")
    return redirect("platformadmin:org_detail", pk=org.pk)
