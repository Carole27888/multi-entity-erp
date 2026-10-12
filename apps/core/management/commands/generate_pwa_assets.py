"""Generate every PWA icon, favicon and iOS splash screen from one source logo (Pillow, no npm).

    python manage.py generate_pwa_assets

Source: static/brand/logo-source.png (>= 1024x1024, a white mark on transparent).
If the file does not exist, a neutral default mark (three stacked layers: one platform, many businesses) is drawn.
The product name on splash screens comes from settings.PRODUCT_NAME.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from apps.core import pwa

GREEN = pwa.THEME_COLOR  # the platform brand colour (settings.BRAND_COLOUR)
WHITE = "#FFFFFF"
SOFT = "#CCE3E0"


def static_root() -> Path:
    return Path(settings.BASE_DIR) / "static"


def font(weight: int, size: int):
    path = static_root() / f"fonts/manrope/manrope-latin-{weight}-normal.woff2"
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size=size)


def draw_default_logo(size: int = 1024) -> Image.Image:
    """White 'layers' mark (same shapes as the 'layers' icon) on a transparent background."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 24  # icon grid is 24x24
    w = max(int(1.8 * s), 2)

    def p(x, y):
        return (x * s, y * s)

    top = [(12, 2.5), (21.5, 7.3), (12, 12.1), (2.5, 7.3), (12, 2.5)]
    d.line([p(*pt) for pt in top], fill=WHITE, width=w, joint="curve")
    d.line([p(*pt) for pt in [(2.5, 12), (12, 16.8), (21.5, 12)]], fill=WHITE, width=w, joint="curve")
    d.line([p(*pt) for pt in [(2.5, 16.7), (12, 21.5), (21.5, 16.7)]], fill=WHITE, width=w, joint="curve")
    r = w / 2
    for x, y in [(12, 2.5), (21.5, 7.3), (12, 12.1), (2.5, 7.3), (2.5, 12), (21.5, 12), (12, 16.8), (2.5, 16.7),
                 (21.5, 16.7), (12, 21.5)]:
        cx, cy = p(x, y)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)
    return img


def load_logo() -> Image.Image:
    src = static_root() / "brand/logo-source.png"
    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        draw_default_logo().save(src)
    return Image.open(src).convert("RGBA")


def fit(logo: Image.Image, box: int) -> Image.Image:
    logo = logo.copy()
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    logo.thumbnail((box, box), Image.LANCZOS)
    return logo


def square_icon(logo, size, logo_ratio=0.62, rounded=True, transparent_corners=True):
    """Dark green (rounded) square with the logo centred."""
    scale = 4  # supersample for smooth corners
    big = size * scale
    mode = "RGBA" if transparent_corners else "RGB"
    img = Image.new(mode, (big, big), (0, 0, 0, 0) if transparent_corners else GREEN)
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.22), fill=GREEN)
    else:
        d.rectangle([0, 0, big, big], fill=GREEN)
    mark = fit(logo, int(big * logo_ratio))
    img.paste(mark, ((big - mark.width) // 2, (big - mark.height) // 2), mark)
    return img.resize((size, size), Image.LANCZOS)


def splash(logo, width, height):
    img = Image.new("RGB", (width, height), GREEN)
    d = ImageDraw.Draw(img)
    short = min(width, height)
    mark = fit(logo, int(short * 0.26))
    title_font = font(800, max(int(short * 0.075), 18))
    tag_font = font(600, max(int(short * 0.026), 10))
    title, tag = settings.PRODUCT_NAME.upper(), settings.PRODUCT_TAGLINE.upper()
    tb = d.textbbox((0, 0), title, font=title_font)
    gb = d.textbbox((0, 0), tag, font=tag_font)
    gap1, gap2 = int(short * 0.06), int(short * 0.025)
    total = mark.height + gap1 + (tb[3] - tb[1]) + gap2 + (gb[3] - gb[1])
    y = (height - total) // 2
    img.paste(mark, ((width - mark.width) // 2, y), mark)
    y += mark.height + gap1
    d.text(((width - (tb[2] - tb[0])) // 2 - tb[0], y - tb[1]), title, font=title_font, fill=WHITE)
    y += (tb[3] - tb[1]) + gap2
    # letter-spaced tagline
    spacing = int(tag_font.size * 0.25)
    chars = list(tag)
    widths = [d.textlength(c, font=tag_font) for c in chars]
    line_w = sum(widths) + spacing * (len(chars) - 1)
    x = (width - line_w) / 2
    for c, cw in zip(chars, widths):
        d.text((x, y - gb[1]), c, font=tag_font, fill=SOFT)
        x += cw + spacing
    return img


def placeholder_screenshot(logo, width, height, label):
    """Branded fallback used only until real screenshots are captured (see README)."""
    img = splash(logo, width, height)
    d = ImageDraw.Draw(img)
    f = font(600, max(int(min(width, height) * 0.03), 12))
    tb = d.textbbox((0, 0), label, font=f)
    d.text(((width - tb[2]) // 2, height - int(height * 0.1)), label, font=f, fill=SOFT)
    return img


class Command(BaseCommand):
    help = "Generate PWA icons, favicons and iOS splash screens into static/pwa/ from static/brand/logo-source.png."

    def add_arguments(self, parser):
        parser.add_argument("--skip-splash", action="store_true", help="Only regenerate icons.")
        parser.add_argument("--force-screenshots", action="store_true", help="Overwrite screenshots with branded placeholders.")

    def handle(self, *args, **options):
        out = static_root() / "pwa"
        (out / "splash").mkdir(parents=True, exist_ok=True)
        logo = load_logo()
        count = 0

        for size in pwa.ICON_SIZES:
            square_icon(logo, size).save(out / f"icon-{size}.png", optimize=True)
            count += 1
        for size in pwa.MASKABLE_SIZES:
            # Full-bleed background; logo within the 80% safe-zone circle.
            square_icon(logo, size, logo_ratio=0.46, rounded=False, transparent_corners=False).save(
                out / f"icon-maskable-{size}.png", optimize=True
            )
            count += 1
        square_icon(logo, 180, logo_ratio=0.58, rounded=False, transparent_corners=False).save(
            out / "apple-touch-icon.png", optimize=True
        )
        square_icon(logo, 32, logo_ratio=0.72).save(out / "favicon-32.png", optimize=True)
        square_icon(logo, 256, logo_ratio=0.72).save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
        count += 3

        if not options["skip_splash"]:
            for s in pwa.splash_images():
                splash(logo, *s["size"]).save(static_root() / s["path"], optimize=True)
                count += 1

        for shot in pwa.SCREENSHOTS:
            path = static_root() / shot["src"]
            if options["force_screenshots"] or not path.exists():
                w, h = (int(v) for v in shot["sizes"].split("x"))
                placeholder_screenshot(logo, w, h, shot["label"]).save(path, optimize=True)
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Generated {count} PWA images in {out}"))
