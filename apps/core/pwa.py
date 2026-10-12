"""PWA constants shared by generate_pwa_assets, the manifest view and {% pwa_head %}."""

from django.conf import settings

THEME_COLOR = settings.BRAND_COLOUR
BACKGROUND_COLOR = settings.BRAND_COLOUR


def app_name() -> str:
    return settings.PRODUCT_NAME


def description() -> str:
    return f"{settings.PRODUCT_NAME}: CRM, sales, finance, operations and your website in one place."


ICON_SIZES = [72, 96, 128, 144, 152, 192, 256, 384, 512]
MASKABLE_SIZES = [192, 512]

# (CSS width, CSS height, pixel ratio, label). Add a new device with one line.
IOS_SPLASH_DEVICES = [
    (440, 956, 3, "iPhone 16 Pro Max"),
    (402, 874, 3, "iPhone 16 Pro"),
    (430, 932, 3, "iPhone 14/15 Pro Max, 15/16 Plus"),
    (393, 852, 3, "iPhone 14/15 Pro, 15, 16"),
    (428, 926, 3, "iPhone 12/13 Pro Max, 14 Plus"),
    (390, 844, 3, "iPhone 12, 13, 14"),
    (414, 896, 3, "iPhone XS Max, 11 Pro Max"),
    (414, 896, 2, "iPhone XR, 11"),
    (375, 812, 3, "iPhone X, XS, 11 Pro, 12/13 mini"),
    (414, 736, 3, "iPhone 8 Plus"),
    (375, 667, 2, "iPhone 8, SE 2nd/3rd gen"),
    (1024, 1366, 2, 'iPad Pro 12.9"'),
    (834, 1194, 2, 'iPad Pro 11"'),
    (820, 1180, 2, "iPad Air"),
    (810, 1080, 2, 'iPad 10.2"'),
    (768, 1024, 2, "iPad mini / older iPads"),
]


def splash_images():
    """Yield dicts describing every portrait + landscape iOS startup image."""
    for width, height, ratio, label in IOS_SPLASH_DEVICES:
        for orientation in ("portrait", "landscape"):
            px_w, px_h = width * ratio, height * ratio
            if orientation == "landscape":
                px_w, px_h = px_h, px_w
            yield {
                "device_width": width, "device_height": height, "ratio": ratio, "orientation": orientation,
                "label": label, "size": (px_w, px_h), "path": f"pwa/splash/apple-splash-{px_w}x{px_h}.png",
            }


def icon_paths():
    paths = [f"pwa/icon-{s}.png" for s in ICON_SIZES]
    paths += [f"pwa/icon-maskable-{s}.png" for s in MASKABLE_SIZES]
    paths += ["pwa/apple-touch-icon.png", "pwa/favicon-32.png", "pwa/favicon.ico"]
    return paths


SCREENSHOTS = [
    {"src": "pwa/screenshot-wide.png", "sizes": "1280x720", "form_factor": "wide", "label": "On desktop"},
    {"src": "pwa/screenshot-narrow.png", "sizes": "750x1334", "form_factor": "narrow", "label": "On a phone"},
]
