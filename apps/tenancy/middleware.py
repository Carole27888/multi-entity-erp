"""Tenant resolution, membership checks and organization status.

TenantMiddleware runs first (straight after SecurityMiddleware). It decides from the host and path whether the
request is for the platform, an organization's staff app or an organization's public site, and then:
  * sets request.organization and the current-organization context variable (scoped managers),
  * switches request.urlconf to config.urls_tenant / config.urls_public,
  * moves the org slug from PATH_INFO into SCRIPT_NAME so reverse() includes it,
  * activates the organization's time zone.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import render
from django.urls import get_script_prefix, set_script_prefix, set_urlconf
from django.utils import timezone

from . import routing
from .context import reset_current_organization, set_current_organization

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        route = routing.resolve(request.get_host(), request.path_info)
        if route.kind == routing.UNKNOWN_HOST:
            return HttpResponseBadRequest("Unknown host.", content_type="text/plain")
        if route.kind == routing.NO_ORG:
            return render(request, "errors/error.html", {"code": 404, "title": "Page not found",
                                                         "message": "There is no organization at this address."}, status=404)
        if route.redirect_to:
            query = request.META.get("QUERY_STRING", "")
            return HttpResponseRedirect(route.redirect_to + (f"?{query}" if query else ""))

        request.organization = route.org
        request.tenant_kind = route.kind
        original_prefix = get_script_prefix()
        base_token = routing.set_base_prefix(original_prefix)
        org_token = set_current_organization(route.org)
        tz_active = False
        try:
            if route.prefix:
                script_name = original_prefix.rstrip("/") + "/" + route.prefix
                request.META["SCRIPT_NAME"] = script_name
                request.path_info = route.path_info
                request.META["PATH_INFO"] = route.path_info
                set_script_prefix(script_name + "/")
            if route.kind == routing.TENANT:
                request.urlconf = settings.TENANT_URLCONF
            elif route.kind == routing.PUBLIC:
                request.urlconf = settings.PUBLIC_URLCONF
            if getattr(request, "urlconf", None):
                set_urlconf(request.urlconf)
            if route.org is not None:
                try:
                    timezone.activate(route.org.timezone)
                    tz_active = True
                except Exception:  # noqa: BLE001
                    pass
            return self.get_response(request)
        finally:
            reset_current_organization(org_token)
            routing.reset_base_prefix(base_token)
            set_script_prefix(original_prefix)
            set_urlconf(None)
            if tz_active:
                timezone.deactivate()


def _login_redirect(request):
    url = f"{settings.LOGIN_URL}?next={quote(request.get_full_path())}"
    if getattr(request, "htmx", False) or request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return HttpResponseRedirect(url)


class MembershipMiddleware:
    """Staff URLs of an organization need a signed-in user with an active membership there.

    Anyone else gets a 404, so the existence of an organization's pages is not revealed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.membership = None
        if getattr(request, "tenant_kind", None) != routing.TENANT:
            return self.get_response(request)
        user = request.user
        if not user.is_authenticated:
            return _login_redirect(request)
        from .models import Membership

        membership = (Membership.objects.select_related("role", "organization")
                      .filter(user=user, organization=request.organization, status=Membership.Status.ACTIVE).first())
        if membership is None:
            raise Http404("Not a member of this organization")
        request.membership = membership
        from apps.accounts.permissions import PermSet

        request.perms = PermSet.for_membership(membership)
        now = timezone.now()
        if membership.last_seen_at is None or now - membership.last_seen_at > timedelta(minutes=5):
            Membership.objects.filter(pk=membership.pk).update(last_seen_at=now)
        if user.last_organization_id != request.organization.pk:
            from apps.accounts.models import User

            User.objects.filter(pk=user.pk).update(last_organization=request.organization)
        return self.get_response(request)


class OrganizationStatusMiddleware:
    """Suspended or cancelled organizations are closed; read-only (unpaid) ones can be viewed but not changed."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org = getattr(request, "organization", None)
        kind = getattr(request, "tenant_kind", None)
        if org is None or kind not in (routing.TENANT, routing.PUBLIC):
            return self.get_response(request)
        from .models import Organization

        impersonating = bool(request.session.get("impersonator_id")) if hasattr(request, "session") else False
        if org.status in (Organization.Status.SUSPENDED, Organization.Status.CANCELLED):
            if kind == routing.PUBLIC:
                return render(request, "errors/error.html", {"code": 404, "title": "Site unavailable",
                                                             "message": "This site is not available at the moment."}, status=404)
            if not (impersonating and request.method in SAFE_METHODS):
                return render(request, "tenancy/closed.html", {"org": org}, status=403)
        if kind == routing.TENANT and not org.is_writable and request.method not in SAFE_METHODS:
            if not request.path_info.startswith(("/billing/",)):
                return render(request, "tenancy/read_only.html", {"org": org}, status=402)
        return self.get_response(request)
