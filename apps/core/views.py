import json
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.permissions import has_perm, require_perm, tenant_object
from apps.industries import checklist
from apps.industries.registry import get as get_pack

from . import modules, pwa
from .models import Attachment


# --- Tenant pages ------------------------------------------------------------------------------------

@require_perm("dashboard.view")
def dashboard(request):
    org = request.organization
    if not org.onboarding_completed_at:
        return redirect(f"/onboarding/?org={org.slug}")
    progress = checklist.progress(org, request)
    enabled = []
    for key in org.enabled_modules or []:
        entry = modules.CATALOGUE.get(key)
        if entry is None or entry.core:
            continue
        mod = modules.get(key)
        enabled.append({"entry": entry, "name": mod.display_name(org) if mod else entry.name,
                        "url": mod.home_url if mod else None})
    from apps.tenancy.models import Membership

    pack = get_pack(org.industry)
    return render(request, "core/dashboard.html", {
        "page_title": "Dashboard", "progress": progress, "show_checklist": not org.settings.get("checklist_dismissed"),
        "enabled_modules": enabled, "pack": pack, "sub_niche": pack.sub_niche(org.sub_niche) if pack else None,
        "member_count": Membership.objects.filter(organization=org, status="active").count(),
    })


@require_POST
@require_perm("dashboard.view")
def checklist_tick(request, key):
    if key == "dismiss":
        if has_perm(request, "settings.edit"):
            org = request.organization
            org.settings = {**org.settings, "checklist_dismissed": True}
            org.save(update_fields=["settings", "updated_at"])
    else:
        checklist.tick(key[:60])
    return redirect("core:dashboard")


@tenant_object(Attachment)
@never_cache
@require_perm("dashboard.view")
def attachment_download(request, pk):
    """Files are only ever served here: the row is looked up through the tenant-scoped manager (another
    organization's file is a 404) and its permission is checked."""
    att = get_object_or_404(Attachment, pk=pk)
    if not has_perm(request, att.permission):
        raise Http404
    try:
        handle = att.file.open("rb")
    except (FileNotFoundError, ValueError) as exc:
        raise Http404 from exc
    if settings.USE_X_SENDFILE:
        response = HttpResponse()
        response["X-Sendfile"] = att.file.path
    else:
        response = FileResponse(handle, as_attachment=True, filename=att.name)
    response["Content-Type"] = att.mime_type or mimetypes.guess_type(att.name)[0] or "application/octet-stream"
    response["Content-Disposition"] = f'attachment; filename="{att.name}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# --- Platform pages ------------------------------------------------------------------------------------

def org_logo(request, slug):
    """An organization's logo is public by nature (website, emails, documents); nothing else is served this way."""
    from apps.tenancy.models import Organization

    org = Organization.objects.filter(slug=slug).exclude(status=Organization.Status.CANCELLED).first()
    if org is None or not org.logo:
        raise Http404
    try:
        handle = org.logo.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    response = FileResponse(handle, content_type=mimetypes.guess_type(org.logo.name)[0] or "image/png")
    response["Cache-Control"] = "public, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def manifest(request):
    icons = [
        {"src": static(f"pwa/icon-{s}.png"), "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any"} for s in pwa.ICON_SIZES
    ] + [
        {"src": static(f"pwa/icon-maskable-{s}.png"), "sizes": f"{s}x{s}", "type": "image/png", "purpose": "maskable"}
        for s in pwa.MASKABLE_SIZES
    ]
    data = {
        "name": pwa.app_name(), "short_name": pwa.app_name(), "description": pwa.description(),
        "id": "/", "start_url": "/orgs/?source=pwa", "scope": "/",
        "display": "standalone", "display_override": ["window-controls-overlay", "standalone"], "orientation": "any",
        "theme_color": pwa.THEME_COLOR, "background_color": pwa.BACKGROUND_COLOR, "lang": "en-GB", "dir": "ltr",
        "categories": ["business", "productivity"], "icons": icons,
        "screenshots": [{"src": static(s["src"]), "sizes": s["sizes"], "type": "image/png", "form_factor": s["form_factor"],
                         "label": s["label"]} for s in pwa.SCREENSHOTS],
    }
    return HttpResponse(json.dumps(data, indent=2), content_type="application/manifest+json")


def _precache_urls() -> list[str]:
    files = [
        "css/tokens.css", "css/base.css", "css/layout.css", "css/components.css", "css/utilities.css",
        "js/app.js", "vendor/htmx/htmx.min.js", "vendor/alpine/alpine.min.js",
        "pwa/icon-192.png", "pwa/icon-96.png", "pwa/favicon-32.png", "pwa/apple-touch-icon.png",
    ] + [f"fonts/manrope/manrope-latin-{w}-normal.woff2" for w in (400, 500, 600, 700, 800)]
    return [static(f) for f in files] + ["/offline/"]


def service_worker(request):
    context = {
        "version": settings.PWA_VERSION, "precache": mark_safe(json.dumps(_precache_urls())), "offline_url": "/offline/",
        "static_prefix": settings.STATIC_URL, "dev_mode": "true" if settings.DEBUG else "false",
        "app_name": pwa.app_name(),
    }
    response = render(request, "core/sw.js", context, content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    return render(request, "core/offline.html")


def health(request):
    """For an uptime monitor: 200 when healthy, 503 when a critical check fails."""
    from .monitoring import checks, healthy

    results = checks()
    ok = healthy(results)
    return JsonResponse({"status": "ok" if ok else "degraded", "version": settings.PWA_VERSION,
                         "checks": {c["name"]: {"ok": c["ok"], "detail": c["detail"]} for c in results}},
                        status=200 if ok else 503)


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")


def home(request):
    if request.user.is_authenticated:
        return redirect("tenancy:choose")
    return redirect("accounts:login")


# --- Errors --------------------------------------------------------------------------------------------

def error_400(request, exception=None):
    return render(request, "errors/error.html", {"code": 400, "title": "Bad request", "message": "The request could not be understood."}, status=400)


def error_403(request, exception=None):
    return render(request, "errors/error.html", {"code": 403, "title": "No access",
                                                 "message": "You don't have permission to open this page. Ask an administrator if you need access."}, status=403)


def error_404(request, exception=None):
    return render(request, "errors/error.html", {"code": 404, "title": "Page not found",
                                                 "message": "The page you are looking for does not exist or has moved."}, status=404)


def error_500(request):
    return render(request, "errors/error.html", {"code": 500, "title": "Something went wrong",
                                                 "message": "The team has been notified. Please try again in a moment."}, status=500)

