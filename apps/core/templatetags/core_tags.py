"""Template helpers loaded everywhere (settings TEMPLATES builtins)."""

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.core import formatting, pwa

register = template.Library()


# --- Terminology & URLs ------------------------------------------------------------------------------

@register.simple_tag(takes_context=True)
def term(context, key, plural=False, lower=False):
    """{% term "lead" %} → "Enquiry" for a tour operator. Never hard-code industry words in core templates."""
    from apps.industries.terms import term as resolve

    return resolve(key, org=context.get("org"), plural=bool(plural), lower=bool(lower))


@register.simple_tag
def gurl(viewname, *args, **kwargs):
    """{% gurl "accounts:security" %} — a platform URL (no organization prefix), usable on tenant pages."""
    from apps.tenancy.routing import reverse_global

    return reverse_global(viewname, *args, **kwargs)


@register.simple_tag
def org_url(org, path=""):
    """Staff-app URL of another organization (the organization switcher)."""
    from apps.tenancy.routing import org_app_url

    return org_app_url(org, path)


# --- Formatting --------------------------------------------------------------------------------------

@register.filter
def money(value, currency=None):
    """{{ amount|money:org.currency }} → 'KES 4,850,000'."""
    return formatting.money(value, currency or settings.DEFAULT_CURRENCY)


@register.filter
def num(value, decimals=0):
    return formatting.kes(value, with_currency=False, decimals=int(decimals))


@register.filter
def compact(value):
    return formatting.compact(value)


@register.filter
def nicedate(value):
    return formatting.display_date(value)


@register.filter
def nicetime(value):
    return formatting.display_time(value)


@register.filter
def initials(value):
    return formatting.initials(str(value))


@register.filter
def percent(value, total):
    try:
        return round(float(value) * 100 / float(total)) if float(total) else 0
    except (TypeError, ValueError):
        return 0


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def tel(phone):
    return f"tel:{phone}" if phone else ""


@register.filter
def whatsapp(phone):
    return f"https://wa.me/{str(phone).lstrip('+')}" if phone else ""


@register.filter
def ago(value):
    """'4m', '3h', '2d' since a datetime."""
    from django.utils import timezone as tz

    if not value:
        return ""
    secs = int((tz.now() - value).total_seconds())
    if secs < 3600:
        return f"{max(secs // 60, 1)}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


@register.simple_tag(takes_context=True)
def querystring_replace(context, **kwargs):
    """Keep current filters while changing one parameter (e.g. page)."""
    query = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return "?" + query.urlencode() if query else "?"


# --- PWA ---------------------------------------------------------------------------------------------

@register.simple_tag
def pwa_head():
    """Every <head> tag the installable app needs (manifest, icons, iOS splash screens)."""
    name = pwa.app_name()
    tags = [
        mark_safe('<link rel="manifest" href="/manifest.webmanifest">'),
        format_html('<meta name="theme-color" content="{}">', pwa.THEME_COLOR),
        mark_safe('<meta name="mobile-web-app-capable" content="yes">'),
        mark_safe('<meta name="apple-mobile-web-app-capable" content="yes">'),
        mark_safe('<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'),
        format_html('<meta name="apple-mobile-web-app-title" content="{}">', name),
        format_html('<meta name="application-name" content="{}">', name),
        format_html('<link rel="apple-touch-icon" href="{}">', static("pwa/apple-touch-icon.png")),
        format_html('<link rel="icon" type="image/png" sizes="32x32" href="{}">', static("pwa/favicon-32.png")),
        format_html('<link rel="icon" href="{}" sizes="any">', static("pwa/favicon.ico")),
    ]
    splash = format_html_join(
        "\n",
        '<link rel="apple-touch-startup-image" media="(device-width: {}px) and (device-height: {}px) and '
        '(-webkit-device-pixel-ratio: {}) and (orientation: {})" href="{}">',
        ((s["device_width"], s["device_height"], s["ratio"], s["orientation"], static(s["path"])) for s in pwa.splash_images()),
    )
    return mark_safe("\n".join(str(t) for t in tags) + "\n" + splash)
