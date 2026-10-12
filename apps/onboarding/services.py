"""Email verification tokens (signed, time-limited) and phone codes."""

from __future__ import annotations

import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

SALT = "onboarding.verify-email"


def email_token(user) -> str:
    return signing.dumps({"u": user.pk, "e": user.email.lower()}, salt=SALT)


def check_email_token(token: str):
    from apps.accounts.models import User

    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFICATION_DAYS * 86400)
    except signing.BadSignature:
        return None
    return User.objects.filter(pk=data.get("u"), email__iexact=data.get("e", "")).first()


def send_verification_email(user) -> None:
    url = f"{settings.SITE_URL}/verify-email/{email_token(user)}/"
    ctx = {"user": user, "url": url, "PRODUCT_NAME": settings.PRODUCT_NAME, "days": settings.EMAIL_VERIFICATION_DAYS}
    send_mail(f"Confirm your email for {settings.PRODUCT_NAME}", render_to_string("onboarding/email/verify.txt", ctx),
              None, [user.email])


def mark_email_verified(user) -> None:
    if not user.email_verified_at:
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at"])


# --- Phone OTP (only when a real SMS provider is configured) ----------------------------------------------

def phone_verification_available() -> bool:
    from apps.integrations.messaging import sms

    return sms().is_live


def send_phone_code(user) -> None:
    from apps.integrations.messaging import sms

    code = f"{secrets.randbelow(10**6):06d}"
    cache.set(f"phone-otp:{user.pk}", {"code": code, "tries": 0}, 600)
    sms().send(user.phone, f"Your {settings.PRODUCT_NAME} code is {code}. It expires in 10 minutes.")


def check_phone_code(user, code: str) -> bool:
    key = f"phone-otp:{user.pk}"
    data = cache.get(key)
    if not data or data["tries"] >= 5:
        return False
    if secrets.compare_digest(data["code"], (code or "").strip()):
        cache.delete(key)
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])
        return True
    data["tries"] += 1
    cache.set(key, data, 600)
    return False
