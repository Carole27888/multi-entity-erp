"""The cron-driven runner used by `manage.py run_jobs`."""

from __future__ import annotations

import logging
import time as time_mod
import traceback
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import SCHEDULES, TASKS

logger = logging.getLogger("apps.core.jobs")
LOCK_NAME = "run_jobs"


def acquire_lock(seconds: int) -> str | None:
    """Portable DB lock: one conditional UPDATE, works on SQLite/PostgreSQL/MySQL."""
    from apps.core.models import JobLock

    JobLock.objects.get_or_create(name=LOCK_NAME)
    token = uuid.uuid4().hex
    now = timezone.now()
    got = JobLock.objects.filter(
        Q(locked_until__isnull=True) | Q(locked_until__lt=now), name=LOCK_NAME
    ).update(locked_until=now + timedelta(seconds=seconds), owner=token)
    return token if got else None


def release_lock(token: str) -> None:
    from apps.core.models import JobLock

    JobLock.objects.filter(name=LOCK_NAME, owner=token).update(locked_until=None, owner="")


def backoff(attempts: int) -> timedelta:
    """1st retry after 2 min, 2nd after 4 min, ..."""
    return timedelta(minutes=2 ** attempts)


def execute_job(job, retry: bool = True) -> bool:
    """Run one job as its organization, recording status. Returns True on success."""
    from apps.core.models import Job
    from apps.tenancy.context import no_tenant, tenant

    func = TASKS.get(job.task_name)
    job.status = Job.Status.RUNNING
    job.started_at = timezone.now()
    job.attempts += 1
    job.save(update_fields=["status", "started_at", "attempts"])
    try:
        if func is None:
            raise KeyError(f"Task '{job.task_name}' is not registered")
        scope = tenant(job.organization) if job.organization_id else no_tenant()
        with scope:
            func(**job.kwargs)
    except Exception:  # noqa: BLE001 - we record every failure
        job.last_error = traceback.format_exc()[-4000:]
        job.finished_at = timezone.now()
        if retry and job.attempts < settings.JOBS_MAX_ATTEMPTS:
            job.status = Job.Status.QUEUED
            job.run_at = timezone.now() + backoff(job.attempts)
        else:
            job.status = Job.Status.FAILED
        job.save(update_fields=["status", "last_error", "finished_at", "run_at"])
        logger.exception("Job %s #%s failed (attempt %s)", job.task_name, job.pk, job.attempts)
        return False
    job.status = Job.Status.DONE
    job.finished_at = timezone.now()
    job.last_error = ""
    job.save(update_fields=["status", "finished_at", "last_error"])
    logger.info("Job %s #%s done", job.task_name, job.pk)
    return True


def _org_tz(org):
    try:
        return ZoneInfo(org.timezone)
    except Exception:  # noqa: BLE001
        return None


def enqueue_due_schedules(now=None) -> list[str]:
    """Queue every due schedule. Per-org schedules get one job per organization that is running."""
    from apps.core.models import Job, ScheduleState
    from apps.tenancy.models import Organization

    now = now or timezone.now()
    queued = []
    orgs = None
    for name, schedule in SCHEDULES.items():
        if not schedule.per_org:
            state, _ = ScheduleState.objects.get_or_create(name=name, organization=None)
            if schedule.is_due(state.last_run_at, now):
                Job.objects.create(task_name=name, run_at=now)
                state.last_run_at = now
                state.save(update_fields=["last_run_at"])
                queued.append(name)
            continue
        if orgs is None:
            orgs = list(Organization.objects.filter(status__in=Organization.RUNNING_STATUSES))
        for org in orgs:
            state, _ = ScheduleState.objects.get_or_create(name=name, organization=org)
            if schedule.is_due(state.last_run_at, now, tz=_org_tz(org)):
                Job.objects.create(task_name=name, run_at=now, organization=org)
                state.last_run_at = now
                state.save(update_fields=["last_run_at"])
                queued.append(f"{name}@{org.slug}")
    return queued


def run_pending(time_limit: int | None = None, now=None) -> dict:
    """Process schedules and queued jobs under the lock. Returns counters."""
    from apps.core.models import Job, JobRunnerHeartbeat

    time_limit = time_limit or settings.JOBS_RUN_TIME_LIMIT
    token = acquire_lock(time_limit + 60)
    if token is None:
        logger.info("run_jobs: another runner holds the lock; exiting")
        return {"locked": True, "run": 0, "failed": 0, "scheduled": []}

    heartbeat = JobRunnerHeartbeat.objects.create()
    started = time_mod.monotonic()
    run = failed = 0
    scheduled = []
    try:
        scheduled = enqueue_due_schedules(now)
        while time_mod.monotonic() - started < time_limit:
            with transaction.atomic():
                job = (
                    Job.objects.select_for_update()
                    .select_related("organization")
                    .filter(status=Job.Status.QUEUED, run_at__lte=now or timezone.now())
                    .order_by("run_at", "id")
                    .first()
                )
                if job is None:
                    break
                job.status = Job.Status.RUNNING
                job.save(update_fields=["status"])
            ok = execute_job(job)
            run += 1
            failed += 0 if ok else 1
    finally:
        heartbeat.finished_at = timezone.now()
        heartbeat.jobs_run, heartbeat.jobs_failed = run, failed
        heartbeat.save()
        release_lock(token)
    return {"locked": False, "run": run, "failed": failed, "scheduled": scheduled}
