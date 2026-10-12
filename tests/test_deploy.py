"""Production settings pass `check --deploy` and every setting is documented in .env.example."""

import os
import re
import subprocess
import sys
from pathlib import Path

from django.conf import settings

ROOT = Path(settings.BASE_DIR)


def test_check_deploy_is_clean_with_prod_settings(tmp_path):
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.prod",
           "SECRET_KEY": "x" * 30 + "prod-check-" + "y" * 30, "DATABASE_URL": f"sqlite:///{tmp_path / 'db.sqlite3'}",
           "LOG_DIR": str(tmp_path), "CACHE_URL": "locmemcache://"}
    result = subprocess.run([sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_env_variable_is_documented():
    used = set()
    for path in (ROOT / "config/settings").glob("*.py"):
        used |= set(re.findall(r'env(?:\.\w+)?\(\s*"([A-Z0-9_]+)"', path.read_text()))
    documented = set(re.findall(r"^#?\s*([A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.MULTILINE))
    assert used <= documented, f"Add to .env.example: {sorted(used - documented)}"


def test_secrets_and_data_are_gitignored():
    ignored = (ROOT / ".gitignore").read_text()
    for entry in (".env", "db.sqlite3", "/media/*", "/logs/*", "/backups/", "apps/*/migrations/*"):
        assert entry in ignored, entry
    assert "!apps/*/migrations/__init__.py" in ignored
