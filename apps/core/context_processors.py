from django.conf import settings
from django.utils.functional import SimpleLazyObject

from apps.tenancy import routing

from . import modules
from .branding import css_vars
from .modules import NavItem


def _impersonator(request):
    pk = request.session.get("impersonator_id") if hasattr(request, "session") else None
    if not pk:
        return None
    from apps.accounts.models import User

    return User.objects.filter(pk=pk).first()


GENERAL_BOTTOM = [NavItem("Home", "core:dashboard", "grid")]


def _tenant_shell(request, org):
    perms = getattr(request, "perms", None)
    match = getattr(request, "resolver_match", None)
    current = match.view_name if match else ""
    module = modules.module_for_namespace(match.namespace) if match and match.namespace else None
    allowed = modules.modules_for(request.user, org, perms)
    if module and module not in allowed:
        module = None
    if module and module.nav:
        nav = modules.visible_nav(module.nav, org, perms, current)
    else:
        nav = modules.visible_nav([NavItem("Dashboard", "core:dashboard", "grid")], org, perms, current)
    module_links = [{"label": m.display_name(org), "url": m.home_url, "icon": m.icon, "key": m.key}
                    for m in allowed if m.home_url and m.key != "dashboard"]
    if module and module.bottom_nav:
        bottom = modules.visible_nav(module.bottom_nav, org, perms, current)
    else:
        bottom = modules.visible_nav(GENERAL_BOTTOM, org, perms, current) + [
            {"label": m["label"], "url": m["url"], "icon": m["icon"], "url_name": "", "active": False}
            for m in module_links[:3]]
    return {
        "current_module": module,
        "current_view": current,
        "sidebar_nav": nav,
        "module_links": module_links,
        "bottom_nav": bottom[:5],
        "can": perms,
        "membership": request.membership,
        "switcher": SimpleLazyObject(lambda: list(request.user.active_memberships())),
    }


def app_shell(request):
    org = getattr(request, "organization", None)
    kind = getattr(request, "tenant_kind", routing.PLATFORM)
    ctx = {
        "PRODUCT_NAME": settings.PRODUCT_NAME,
        "PRODUCT_TAGLINE": settings.PRODUCT_TAGLINE,
        "PWA_VERSION": settings.PWA_VERSION,
        "SITE_URL": settings.SITE_URL,
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "org": org,
        "tenant_kind": kind,
        "brand_css": css_vars(org.brand_colour if org else settings.BRAND_COLOUR),
    }
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return ctx
    ctx["impersonator"] = SimpleLazyObject(lambda: _impersonator(request))
    if kind == routing.TENANT and getattr(request, "membership", None) is not None:
        ctx.update(_tenant_shell(request, org))
    else:
        ctx["switcher"] = SimpleLazyObject(lambda: list(user.active_memberships()))
    return ctx
