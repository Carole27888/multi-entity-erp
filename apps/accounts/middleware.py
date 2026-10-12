"""Two-factor enforcement and idle session timeouts."""

import time
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect

from apps.tenancy import routing

from .two_factor import LAST_ACTIVITY, VERIFIED

# Platform paths that work without a finished two-factor sign-in.
EXEMPT_PREFIXES = ("/accounts/", "/static/", "/sw.js", "/manifest.webmanifest", "/offline/", "/health/", "/favicon",
                   "/signup/", "/verify-email/", "/verify-phone/", "/invite/", "/media-public/",
                   # The set-up wizard runs before the new owner has an authenticator; set-up is required right after.
                   "/onboarding/")


def _redirect(request, url):
    if getattr(request, "htmx", False) or request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = url
        return response
    return redirect(url)


def _exempt(request) -> bool:
    kind = getattr(request, "tenant_kind", routing.PLATFORM)
    if kind == routing.PUBLIC:
        return True
    return kind == routing.PLATFORM and request.path_info.startswith(EXEMPT_PREFIXES)


class TwoFactorMiddleware:
    """Close any signed-in session that skipped the two-factor step (old sessions, roles that changed, the Django
    admin login form). The user signs in again and is asked for a code, or to set two-factor up."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated and not _exempt(request)
                and user.uses_two_factor and not request.session.get(VERIFIED)):
            next_path = request.get_full_path()
            if not user.totp_enabled:
                # Their password was checked when this session started; a new role now needs an authenticator.
                return _redirect(request, f"/accounts/two-factor/setup/?next={quote(next_path)}")
            logout(request)
            messages.info(request, "Please sign in with your authenticator code to continue.")
            return _redirect(request, f"{settings.LOGIN_URL}?next={quote(next_path)}")
        return self.get_response(request)


class SessionTimeoutMiddleware:
    """Signs a user out after their role's idle timeout (the strictest among their organizations)."""

    TOUCH_EVERY = 60  # seconds between session writes

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and getattr(request, "tenant_kind", None) != routing.PUBLIC:
            limits = [r.idle_timeout_minutes for r in user._membership_roles if r.idle_timeout_minutes]
            now = int(time.time())
            last = request.session.get(LAST_ACTIVITY)
            if limits and last and now - last > min(limits) * 60 and not request.session.get("impersonator_id"):
                next_path = request.get_full_path()
                logout(request)
                messages.info(request, "You were signed out after a period of inactivity.")
                return _redirect(request, f"{settings.LOGIN_URL}?next={quote(next_path)}")
            if not last or now - last >= self.TOUCH_EVERY:
                request.session[LAST_ACTIVITY] = now
        return self.get_response(request)
