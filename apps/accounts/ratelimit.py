"""Cache-based login throttling (per IP + email, 15 minute window)."""

from django.conf import settings
from django.core.cache import cache

WINDOW = 15 * 60


def _key(ip: str, email: str) -> str:
    return f"login-fail:{ip}:{(email or '').lower()}"


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def is_blocked(request, email: str) -> bool:
    return cache.get(_key(client_ip(request), email), 0) >= settings.LOGIN_RATE_LIMIT


def register_failure(request, email: str) -> None:
    key = _key(client_ip(request), email)
    cache.add(key, 0, WINDOW)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, WINDOW)


def reset(request, email: str) -> None:
    cache.delete(_key(client_ip(request), email))


def too_many(request, bucket: str, limit: int, window: int = 3600) -> bool:
    """Count one hit for this IP in `bucket`; True once more than `limit` hits fall inside `window` seconds."""
    key = f"rl:{bucket}:{client_ip(request)}"
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit
