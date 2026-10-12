"""Per-organization brand colours as CSS variables, with text colours that keep WCAG AA contrast.

An organization picks one brand colour. From it we derive the sidebar, primary button, hover, soft tint and
on-colour text. If the colour is too light for white text, darker shades are used where text sits on it.
"""

from __future__ import annotations

import colorsys
import re

HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")
DEFAULT = "#4F46E5"


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    m = HEX.match(hex_colour or "")
    h = (m.group(1) if m else DEFAULT[1:])
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def _lum(rgb) -> float:
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_lum(_rgb(a) if isinstance(a, str) else a), _lum(_rgb(b) if isinstance(b, str) else b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _with_lightness(rgb, lightness: float, sat_scale: float = 1.0):
    h, l_, s = colorsys.rgb_to_hls(*rgb)
    return colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), max(0.0, min(1.0, s * sat_scale)))


def darken_until(rgb, against=(1, 1, 1), ratio: float = 4.5):
    """Lower the lightness until text in `against` colour reaches `ratio`."""
    h, l_, s = colorsys.rgb_to_hls(*rgb)
    current = rgb
    while contrast(_hex(current), _hex(against)) < ratio and l_ > 0.02:
        l_ -= 0.02
        current = colorsys.hls_to_rgb(h, l_, s)
    return current


def palette(brand: str) -> dict[str, str]:
    base = _rgb(brand)
    primary = darken_until(base, ratio=4.5)  # white button text stays readable
    h, l_, s = colorsys.rgb_to_hls(*primary)
    # Sidebar: always a deep shade of the brand (lightness ~0.2, a little less saturated), whatever the colour.
    sidebar = darken_until(colorsys.hls_to_rgb(h, min(l_, 0.2), s * 0.65), ratio=7)
    # Hover: visibly darker than the button, so it still passes on white text.
    hover = colorsys.hls_to_rgb(h, max(l_ - 0.08, 0.08), s)
    soft = _with_lightness(base, 0.94, 0.7)
    light = _with_lightness(base, 0.78, 0.6)
    sidebar_text = _with_lightness(base, 0.88, 0.35)
    sidebar_muted = _with_lightness(base, 0.72, 0.3)
    return {
        "--c-brand": _hex(base),
        "--c-primary": _hex(primary),
        "--c-primary-hover": _hex(hover),
        "--c-primary-soft": _hex(soft),
        "--c-primary-light": _hex(light),
        "--c-primary-text": _hex(darken_until(primary, against=_rgb(_hex(soft)), ratio=4.5)),
        "--c-sidebar": _hex(sidebar),
        "--c-sidebar-text": _hex(sidebar_text),
        "--c-sidebar-muted": _hex(sidebar_muted),
    }


def css_vars(brand: str) -> str:
    return ";".join(f"{k}:{v}" for k, v in palette(brand).items())
