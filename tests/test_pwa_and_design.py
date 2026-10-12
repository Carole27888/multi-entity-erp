"""Installable app, no-Node rule, vendored libraries and brand colour contrast."""

import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.core import pwa
from apps.core.branding import contrast, palette

ROOT = Path(settings.BASE_DIR)


def test_manifest_service_worker_and_offline(client):
    manifest = json.loads(client.get("/manifest.webmanifest").content)
    assert manifest["name"] == settings.PRODUCT_NAME and manifest["display"] == "standalone"
    assert any(i["purpose"] == "maskable" for i in manifest["icons"])
    sw = client.get("/sw.js")
    assert sw["Content-Type"].startswith("application/javascript") and sw["Service-Worker-Allowed"] == "/"
    assert rb"\/files\/" in sw.content  # downloads are never cached
    assert client.get("/offline/").status_code == 200


def test_icons_exist():
    for path in pwa.icon_paths():
        assert (ROOT / "static" / path).exists(), path
    for s in pwa.splash_images():
        assert (ROOT / "static" / s["path"]).exists(), s["path"]


def test_no_node_or_build_step():
    for name in ("package.json", "package-lock.json", "yarn.lock", "node_modules", "webpack.config.js", "vite.config.js"):
        assert not (ROOT / name).exists(), name


def test_vendored_libraries_are_listed():
    versions = (ROOT / "static/vendor/VERSIONS.md").read_text()
    for lib in ("htmx", "Alpine.js", "Chart.js", "SortableJS", "Manrope"):
        assert lib in versions, lib
    for f in ("htmx/htmx.min.js", "alpine/alpine.min.js", "chartjs/chart.umd.min.js", "sortable/Sortable.min.js"):
        assert (ROOT / "static/vendor" / f).exists(), f


@pytest.mark.parametrize("colour", ["#134E4A", "#FFD60A", "#FFFFFF", "#00FF00", "#9A3412", "#87CEEB", "#000000", "#E11D48"])
def test_brand_palette_keeps_text_readable(colour):
    p = palette(colour)
    assert contrast(p["--c-primary"], "#FFFFFF") >= 4.5      # white text on buttons
    assert contrast(p["--c-primary-hover"], "#FFFFFF") >= 4.5
    assert contrast(p["--c-sidebar"], p["--c-sidebar-text"]) >= 4.5
    assert contrast(p["--c-primary-text"], p["--c-primary-soft"]) >= 4.5


def test_phone_width_rules_exist():
    """Layouts collapse at phone width (360–390px) and the bottom bar appears."""
    layout = (ROOT / "static/css/layout.css").read_text()
    assert "@media (max-width: 720px)" in layout and ".bottom-nav" in layout
    assert "@media (max-width: 720px)" in (ROOT / "static/css/platform.css").read_text()
