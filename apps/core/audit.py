"""Write audit entries for actions that are not plain model saves."""

from apps.accounts.ratelimit import client_ip


def audit(action: str, request=None, *, user=None, organization=None, target="", **details):
    from apps.tenancy.context import get_current_organization

    from .models import AuditLog

    impersonator_id = None
    ip = None
    if request is not None:
        if user is None and getattr(request, "user", None) is not None and request.user.is_authenticated:
            user = request.user
        if organization is None:
            organization = getattr(request, "organization", None)
        if hasattr(request, "session"):
            impersonator_id = request.session.get("impersonator_id")
        ip = client_ip(request) or None
    if organization is None:
        organization = get_current_organization()
    return AuditLog.objects.create(action=action, user=user, organization=organization, impersonator_id=impersonator_id,
                                   target=str(target)[:200], details=details, ip_address=ip)
