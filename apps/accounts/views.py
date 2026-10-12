from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from apps.core.audit import audit

from . import ratelimit, two_factor
from .forms import CodeForm, LoginForm

AFTER_LOGIN = "/orgs/"


def _safe_next(request, url: str) -> str:
    if url and url_has_allowed_host_and_scheme(url, {request.get_host()}, request.is_secure()):
        return url
    return ""


@never_cache
@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, request.GET.get("next")) or AFTER_LOGIN)
    form = LoginForm(request, data=request.POST or None)
    blocked = False
    if request.method == "POST":
        email = request.POST.get("email", "")
        if ratelimit.is_blocked(request, email):
            blocked = True
            form.errors.clear()
        elif form.is_valid():
            ratelimit.reset(request, email)
            user, remember = form.user, form.cleaned_data.get("remember_me")
            next_url = _safe_next(request, request.POST.get("next") or request.GET.get("next"))
            if user.uses_two_factor:
                # Password is right; the authenticator code comes next (or setting it up, for roles that must use it).
                two_factor.start_pending(request, user, remember, next_url)
                return redirect("accounts:two_factor_verify" if user.totp_enabled else "accounts:two_factor_setup")
            two_factor.complete_login(request, user, remember, method="password")
            return redirect(next_url or AFTER_LOGIN)
        else:
            ratelimit.register_failure(request, email)
            audit("login_failed", request, organization=None, email=email[:150])
    return render(request, "accounts/login.html", {"form": form, "blocked": blocked, "next": request.GET.get("next", "")})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


@never_cache
@csrf_protect
def two_factor_verify(request):
    found = two_factor.pending(request)
    if not found:
        messages.info(request, "Please sign in again.")
        return redirect("accounts:login")
    user, data = found
    if not user.totp_enabled:
        return redirect("accounts:two_factor_setup")
    form = CodeForm(request.POST or None)
    if request.method == "POST":
        if two_factor.code_blocked(request, user):
            form.add_error("code", "Too many wrong codes. Wait 15 minutes, or ask an admin to reset your two-factor login.")
        elif form.is_valid() and (method := two_factor.check_code(user, form.cleaned_data["code"])):
            two_factor.code_ok(request, user)
            two_factor.complete_login(request, user, data["remember"], method=f"password+{method}")
            if method == "backup":
                left = len(user.totp_backup_codes)
                messages.warning(request, f"You signed in with a backup code. {left} left. Create new ones under Security if you're running low.")
            return redirect(data["next"] or AFTER_LOGIN)
        else:
            two_factor.code_failed(request, user)
            if form.is_valid():
                form.add_error("code", "That code is not right. Check the time on your phone and try the newest code.")
    return render(request, "accounts/two_factor_verify.html", {"form": form, "email": user.email})


@never_cache
@csrf_protect
def two_factor_setup(request):
    """Turn on two-factor login: scan the QR code, confirm one code, save the backup codes.
    Works during sign-in (roles that must use it) and from the Security page."""
    found = two_factor.pending(request)
    if found:
        user, data = found
    elif request.user.is_authenticated:
        user, data = request.user, None
    else:
        return redirect("accounts:login")
    secret = two_factor.setup_secret(request)
    form = CodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        codes = two_factor.confirm_enrolment(request, user, form.cleaned_data["code"])
        if codes:
            if data is not None:
                two_factor.complete_login(request, user, data["remember"], method="password+totp (setup)")
                next_url = data["next"] or AFTER_LOGIN
            else:
                request.session[two_factor.VERIFIED] = True
                next_url = _safe_next(request, request.GET.get("next")) or "/accounts/security/"
            return render(request, "accounts/backup_codes.html", {"codes": codes, "next": next_url, "first_time": True})
        form.add_error("code", "That code is not right. Scan the QR code again and enter the newest 6-digit code.")
    return render(request, "accounts/two_factor_setup.html", {
        "form": form, "qr": two_factor.qr_svg(user, secret), "secret": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
        "required": user.two_factor_required, "during_login": data is not None, "email": user.email,
    })


@login_required
@never_cache
def security_view(request):
    user = request.user
    form = CodeForm(request.POST or None)
    impersonating = bool(request.session.get("impersonator_id"))
    if request.method == "POST":
        if impersonating:
            messages.error(request, "Security settings can't be changed while impersonating.")
            return redirect("accounts:security")
        action = request.POST.get("action")
        if not user.totp_enabled:
            return redirect("accounts:two_factor_setup")
        if form.is_valid() and two_factor.check_code(user, form.cleaned_data["code"]):
            if action == "backup_codes":
                return render(request, "accounts/backup_codes.html", {"codes": two_factor.new_backup_codes(user), "next": "/accounts/security/"})
            if action == "disable":
                if user.two_factor_required:
                    messages.error(request, "One of your roles must use two-factor login, so it can't be turned off.")
                else:
                    two_factor.disable(user, request=request)
                    messages.success(request, "Two-factor login is off.")
                return redirect("accounts:security")
        else:
            form.add_error("code", "Enter a current code from your authenticator app (or a backup code) to confirm.")
    return render(request, "accounts/security.html", {
        "page_title": "Security", "form": form, "backup_left": len(user.totp_backup_codes or []),
        "session_hours": (user.session_max_seconds or 0) // 3600, "impersonating": impersonating,
    })


def _email_context():
    return {"SITE_URL": settings.SITE_URL, "PRODUCT_NAME": settings.PRODUCT_NAME}


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/email/password_reset.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_email_context = None

    def post(self, request, *args, **kwargs):
        if ratelimit.too_many(request, "password_reset", limit=5, window=3600):
            messages.error(request, "Too many reset requests. Please try again in an hour.")
            return redirect("accounts:password_reset")
        self.extra_email_context = _email_context()
        return super().post(request, *args, **kwargs)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        response = super().form_valid(form)
        audit("password_reset", self.request, user=form.user, organization=None)
        return response


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:security")

    def dispatch(self, request, *args, **kwargs):
        if request.session.get("impersonator_id"):
            messages.error(request, "Passwords can't be changed while impersonating.")
            return redirect("accounts:security")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed.")
        audit("password_changed", self.request, organization=None)
        return super().form_valid(form)
