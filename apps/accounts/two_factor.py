"""Two-factor login: pending sign-ins, code checks, enrolment, and session length rules."""

import time
from io import BytesIO

from django.conf import settings
from django.contrib.auth import login
from django.utils import timezone
from django.utils.safestring import mark_safe

from apps.core.audit import audit

from . import totp

PENDING = "2fa_pending"      # {"user": pk, "remember": bool, "next": str, "ts": epoch}
SETUP_SECRET = "2fa_setup_secret"
VERIFIED = "otp_ok"          # set on the session once the code was checked
LAST_ACTIVITY = "last_activity"
PENDING_MAX_AGE = 10 * 60    # a password-verified sign-in must finish within 10 minutes


# ---- Pending sign-in (password accepted, code still needed) ---------------------------------------

def start_pending(request, user, remember: bool, next_url: str = "") -> None:
    request.session.cycle_key()
    request.session[PENDING] = {"user": user.pk, "remember": bool(remember), "next": next_url or "", "ts": int(time.time())}


def pending(request) -> tuple | None:
    """(user, data) for a sign-in waiting for its code, or None."""
    from .models import User

    data = request.session.get(PENDING)
    if not data or time.time() - data.get("ts", 0) > PENDING_MAX_AGE:
        request.session.pop(PENDING, None)
        return None
    user = User.objects.filter(pk=data["user"], is_active=True).first()
    return (user, data) if user else None


def apply_session_expiry(request, user, remember: bool) -> None:
    """Browser-close sessions unless "Keep me signed in"; roles handling money are capped (Role.session_max_hours)."""
    if not remember:
        request.session.set_expiry(0)
        return
    limit = user.session_max_seconds
    if limit:
        request.session.set_expiry(min(limit, settings.SESSION_COOKIE_AGE))


def complete_login(request, user, remember: bool, method: str) -> None:
    request.session.pop(PENDING, None)
    # Use the backend that checked the password, or the project's first one (a pending user is re-loaded from the DB).
    login(request, user, backend=getattr(user, "backend", None) or settings.AUTHENTICATION_BACKENDS[0])
    request.session[VERIFIED] = user.uses_two_factor
    request.session[LAST_ACTIVITY] = int(time.time())
    apply_session_expiry(request, user, remember)
    audit("login", request, user=user, organization=None, method=method)


# ---- Codes ----------------------------------------------------------------------------------------

def check_code(user, code: str) -> str | None:
    """Accept an authenticator code (once per time step) or an unused backup code. Returns 'totp', 'backup' or None."""
    code = (code or "").strip()
    step = totp.verify(user.totp_secret, code, last_step=user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        user.save(update_fields=["totp_last_step"])
        return "totp"
    hashed = totp.hash_backup_code(code)
    if code and hashed in (user.totp_backup_codes or []):
        user.totp_backup_codes = [h for h in user.totp_backup_codes if h != hashed]
        user.save(update_fields=["totp_backup_codes"])
        return "backup"
    return None


def code_blocked(request, user) -> bool:
    from . import ratelimit

    return ratelimit.is_blocked(request, f"2fa:{user.pk}")


def code_failed(request, user) -> None:
    from . import ratelimit

    ratelimit.register_failure(request, f"2fa:{user.pk}")


def code_ok(request, user) -> None:
    from . import ratelimit

    ratelimit.reset(request, f"2fa:{user.pk}")


# ---- Enrolment ------------------------------------------------------------------------------------

def setup_secret(request) -> str:
    secret = request.session.get(SETUP_SECRET)
    if not secret:
        secret = request.session[SETUP_SECRET] = totp.generate_secret()
    return secret


def qr_svg(user, secret: str) -> str:
    import qrcode
    import qrcode.image.svg

    uri = totp.provisioning_uri(secret, user.email, settings.TWO_FACTOR_ISSUER)
    buf = BytesIO()
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2).save(buf)
    svg = buf.getvalue().decode()
    return mark_safe(svg[svg.index("<svg"):])  # drop the XML prolog for inline use


def confirm_enrolment(request, user, code: str) -> list[str] | None:
    """Turn two-factor on if `code` matches the pending secret. Returns the new backup codes (shown once)."""
    secret = request.session.get(SETUP_SECRET)
    step = totp.verify(secret, code) if secret else None
    if step is None:
        return None
    codes = totp.new_backup_codes()
    user.totp_secret, user.totp_enabled, user.totp_last_step = secret, True, step
    user.totp_backup_codes = [totp.hash_backup_code(c) for c in codes]
    user.totp_enabled_at = timezone.now()
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_last_step", "totp_backup_codes", "totp_enabled_at"])
    request.session.pop(SETUP_SECRET, None)
    audit("two_factor_enabled", request, user=user, organization=None)
    return codes


def new_backup_codes(user) -> list[str]:
    codes = totp.new_backup_codes()
    user.totp_backup_codes = [totp.hash_backup_code(c) for c in codes]
    user.save(update_fields=["totp_backup_codes"])
    return codes


def disable(user, by=None, request=None) -> None:
    """Turn two-factor off (the user themselves, or an admin resetting a lost phone)."""
    user.totp_secret, user.totp_enabled, user.totp_last_step, user.totp_backup_codes, user.totp_enabled_at = "", False, None, [], None
    user.save(update_fields=["totp_secret", "totp_enabled", "totp_last_step", "totp_backup_codes", "totp_enabled_at"])
    audit("two_factor_reset", request, user=by or user, target=user.email)
