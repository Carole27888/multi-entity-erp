"""Where a request belongs: the platform, an organization's staff app, or an organization's public site.

Staff app (TENANT_ROUTING="path", the default):   https://APP_HOST/<org-slug>/…
Staff app (TENANT_ROUTING="subdomain"):           https://<org-slug>.APP_HOST/…
Public site, always available:                    https://APP_HOST/s/<org-slug>/…
Public site with WILDCARD_SUBDOMAINS=True:        https://<org-slug>.PUBLIC_DOMAIN/…
Public site on a verified custom domain:          https://www.example.co.ke/…
Platform pages (sign-in, onboarding, platform admin) live on APP_HOST outside any org slug.

For path-based URLs the slug moves from PATH_INFO into SCRIPT_NAME and becomes the script prefix, so every
reverse() and {% url %} inside an organization includes it with no slug argument. Platform URLs are built with
reverse_global() / {% gurl %}.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from django.conf import settings
from django.urls import get_script_prefix, reverse, set_script_prefix

PLATFORM = "platform"
TENANT = "tenant"
PUBLIC = "public"
UNKNOWN_HOST = "unknown_host"
NO_ORG = "no_org"

_base_prefix = ContextVar("base_script_prefix", default="/")


@dataclass
class Route:
    kind: str
    org: object = None
    prefix: str = ""  # added to SCRIPT_NAME, e.g. "acme" or "s/acme"
    path_info: str = ""  # PATH_INFO after the prefix
    redirect_to: str = ""


def _hosts(values) -> set[str]:
    return {v.strip().lower().split(":")[0] for v in values if v}


def app_hosts() -> set[str]:
    return _hosts([settings.APP_HOST, *settings.APP_HOST_ALIASES])


def _split_first(path: str) -> tuple[str, str]:
    """'/acme/crm/leads/' -> ('acme', '/crm/leads/')"""
    parts = path.lstrip("/").split("/", 1)
    first = parts[0]
    rest = "/" + (parts[1] if len(parts) > 1 else "")
    return first, rest


def _org_by_slug(slug: str):
    from .models import RESERVED_SLUGS, Organization

    if not slug or slug in RESERVED_SLUGS:
        return None
    return Organization.objects.select_related("plan", "country").filter(slug=slug).first()


def resolve(host: str, path: str) -> Route:
    from .models import RESERVED_SLUGS, Domain

    host = (host or "").lower().split(":")[0].rstrip(".")
    app_domain = settings.APP_HOST.lower().split(":")[0]

    if host in app_hosts():
        first, rest = _split_first(path)
        if first == "s":  # public-site fallback: /s/<slug>/…
            slug, rest2 = _split_first(rest)
            org = _org_by_slug(slug)
            if org is None:
                return Route(NO_ORG)
            if not path.startswith(f"/s/{slug}/"):
                return Route(PUBLIC, org, redirect_to=f"/s/{slug}/")
            return Route(PUBLIC, org, prefix=f"s/{slug}", path_info=rest2)
        if settings.TENANT_ROUTING == "path" and first and first not in RESERVED_SLUGS:
            org = _org_by_slug(first)
            if org is not None:
                if not path.startswith(f"/{first}/"):
                    return Route(TENANT, org, redirect_to=f"/{first}/")
                return Route(TENANT, org, prefix=first, path_info=rest)
        # Platform pages; an unknown first segment falls through to the platform URLConf's 404.
        return Route(PLATFORM)

    # <slug>.APP_HOST → staff app (subdomain routing)
    if settings.TENANT_ROUTING == "subdomain" and host.endswith("." + app_domain):
        slug = host[: -len(app_domain) - 1]
        org = _org_by_slug(slug) if "." not in slug else None
        return Route(TENANT, org, path_info=path) if org else Route(NO_ORG)

    # <slug>.PUBLIC_DOMAIN → public site (only when wildcard DNS/TLS exists)
    public_domain = settings.PUBLIC_DOMAIN.lower()
    if settings.WILDCARD_SUBDOMAINS and host.endswith("." + public_domain):
        slug = host[: -len(public_domain) - 1]
        if "." not in slug and slug not in ("www", "app"):
            org = _org_by_slug(slug)
            if org is None:
                return Route(NO_ORG)
            if not org.has_feature("public_subdomain"):
                return Route(PUBLIC, org, redirect_to=f"{settings.SITE_URL}/s/{slug}/")
            return Route(PUBLIC, org, path_info=path)

    # Verified custom domain
    domain = Domain.objects.select_related("organization", "organization__plan").filter(
        hostname=host, verified_at__isnull=False).first()
    if domain is not None:
        return Route(PUBLIC, domain.organization, path_info=path)
    return Route(UNKNOWN_HOST)


# --- Building URLs ------------------------------------------------------------------------------------

def base_prefix() -> str:
    return _base_prefix.get()


def set_base_prefix(prefix: str):
    return _base_prefix.set(prefix)


def reset_base_prefix(token) -> None:
    _base_prefix.reset(token)


def reverse_global(viewname: str, *args, **kwargs) -> str:
    """reverse() against the platform URLConf, ignoring the current organization's prefix."""
    current = get_script_prefix()
    set_script_prefix(base_prefix())
    try:
        return reverse(viewname, urlconf=settings.ROOT_URLCONF, args=args or None, kwargs=kwargs or None)
    finally:
        set_script_prefix(current)


def org_app_url(org, path: str = "") -> str:
    path = path.lstrip("/")
    if settings.TENANT_ROUTING == "subdomain":
        scheme = settings.SITE_URL.split("://", 1)[0]
        return f"{scheme}://{org.slug}.{settings.APP_HOST}/{path}"
    return f"{base_prefix()}{org.slug}/{path}"


def org_public_url(org, path: str = "") -> str:
    """Absolute URL of the organization's public site (custom domain > subdomain > /s/<slug>/)."""
    path = path.lstrip("/")
    scheme = settings.SITE_URL.split("://", 1)[0]
    primary = org.domains.filter(verified_at__isnull=False, kind="custom").order_by("-is_primary").first() \
        if org.has_feature("custom_domain") else None
    if primary:
        return f"{scheme}://{primary.hostname}/{path}"
    if settings.WILDCARD_SUBDOMAINS and org.has_feature("public_subdomain"):
        return f"{scheme}://{org.slug}.{settings.PUBLIC_DOMAIN}/{path}"
    return f"{settings.SITE_URL}/s/{org.slug}/{path}"
