"""System health checks for /health/ (an uptime monitor) and the platform status page.
Phase 8 adds backups, disk space and the watchdog alerts."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone


def _check(name, ok, detail, critical=True):
    return {"name": name, "ok": bool(ok), "detail": detail, "critical": critical}


def checks() -> list[dict]:
    from .models import Job, JobRunnerHeartbeat

    out = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        out.append(_check("database", True, connection.vendor))
    except Exception as exc:  # noqa: BLE001
        return [_check("database", False, f"{type(exc).__name__}")]
    if settings.JOBS_BACKEND == "cron":
        last = JobRunnerHeartbeat.objects.first()
        stale = last is None or timezone.now() - last.started_at > timedelta(minutes=15)
        out.append(_check("jobs", not stale, "cron has not run in 15 minutes" if stale else f"last run {last.started_at:%H:%M}"))
    failed = Job.objects.filter(status=Job.Status.FAILED, finished_at__gte=timezone.now() - timedelta(days=1)).count()
    out.append(_check("failed_jobs", failed == 0, f"{failed} failed in 24 h", critical=False))
    return out


def healthy(results) -> bool:
    return all(r["ok"] for r in results if r["critical"])
