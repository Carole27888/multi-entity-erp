"""Database-backed background jobs, run by cron through `manage.py run_jobs`. No workers, no Celery.

Register a task:

    from apps.core.jobs import task, interval, daily, monthly

    @task("crm.send_reminder")
    def send_reminder(task_id): ...

    @interval(minutes=5)                    # platform-wide, every 5 minutes
    def check_watchdog(): ...

    @daily(at="06:00", per_org=True)        # once per active organization, at 06:00 in ITS time zone
    def morning_digest(): ...

    @monthly(day=1, at="05:00", per_org=True)
    def recurring_invoices(): ...

Queue work:  enqueue("crm.send_reminder", task_id=4)
The job remembers the current organization and runs inside `with tenant(org):`, so tasks use scoped
managers as usual. Backends (settings.JOBS_BACKEND): "sync" runs inline, "cron" stores for run_jobs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Callable

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("apps.core.jobs")

TASKS: dict[str, Callable] = {}
SCHEDULES: dict[str, "Schedule"] = {}


@dataclass
class Schedule:
    name: str
    kind: str  # interval | daily | monthly
    every: timedelta | None = None
    at: time | None = None
    day: int | None = None
    per_org: bool = False

    def is_due(self, last_run: datetime | None, now: datetime | None = None, tz=None) -> bool:
        """`tz`: the organization's time zone for per-org schedules (default: the active one)."""
        now = timezone.localtime(now or timezone.now(), tz)
        if self.kind == "interval":
            return last_run is None or now - last_run >= self.every
        # Time-of-day schedules: due once the slot for this period has passed and we have not run since that slot.
        if self.kind == "daily":
            slot = now.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        else:  # monthly
            if now.day < self.day:
                return False
            slot = now.replace(day=self.day, hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        if now < slot:
            return False
        return last_run is None or last_run < slot


def _qualified(func: Callable) -> str:
    module = func.__module__.replace("apps.", "").replace(".tasks", "")
    return f"{module}.{func.__name__}"


def task(name: str | None = None):
    def decorator(func):
        TASKS[name or _qualified(func)] = func
        func.task_name = name or _qualified(func)
        return func

    return decorator


def _parse_at(at: str) -> time:
    hour, minute = at.split(":")
    return time(int(hour), int(minute))


def interval(minutes: int = 0, hours: int = 0, name: str | None = None, per_org: bool = False):
    def decorator(func):
        func = task(name)(func)
        SCHEDULES[func.task_name] = Schedule(func.task_name, "interval", every=timedelta(minutes=minutes, hours=hours),
                                             per_org=per_org)
        return func

    return decorator


def daily(at: str = "06:00", name: str | None = None, per_org: bool = False):
    def decorator(func):
        func = task(name)(func)
        SCHEDULES[func.task_name] = Schedule(func.task_name, "daily", at=_parse_at(at), per_org=per_org)
        return func

    return decorator


def monthly(day: int = 1, at: str = "06:00", name: str | None = None, per_org: bool = False):
    def decorator(func):
        func = task(name)(func)
        SCHEDULES[func.task_name] = Schedule(func.task_name, "monthly", at=_parse_at(at), day=day, per_org=per_org)
        return func

    return decorator


def enqueue(task_name: str, run_at: datetime | None = None, organization=None, **kwargs):
    """Queue (or, with the sync backend, run now) a registered task. Returns the Job.

    The job runs as `organization`, or the current organization when not given.
    """
    from apps.core.models import Job
    from apps.tenancy.context import get_current_organization

    if task_name not in TASKS:
        raise KeyError(f"Unknown task '{task_name}'")
    org = organization if organization is not None else get_current_organization()
    now = timezone.now()
    job = Job.objects.create(task_name=task_name, kwargs=kwargs, run_at=run_at or now, organization=org)
    if getattr(settings, "JOBS_BACKEND", "sync") == "sync" and job.run_at <= now:
        from .runner import execute_job

        execute_job(job, retry=False)
    return job
