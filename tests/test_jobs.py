"""The database job runner: tenant context, per-organization schedules, retries and the lock."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.models import Department
from apps.core import jobs
from apps.core.jobs.runner import acquire_lock, enqueue_due_schedules, release_lock, run_pending
from apps.core.models import Job, ScheduleState
from apps.tenancy.context import get_current_organization, tenant

SEEN = []


@jobs.task("tests.record_org")
def record_org():
    org = get_current_organization()
    SEEN.append((org.slug if org else None, Department.objects.count() if org else None))


@jobs.task("tests.fail")
def fail():
    raise RuntimeError("boom")


@pytest.fixture(autouse=True)
def _clear():
    SEEN.clear()
    yield
    jobs.SCHEDULES.pop("tests.nightly", None)


@pytest.mark.django_db
def test_enqueue_runs_inside_the_current_organization(org1, org2):
    with tenant(org2):
        Department.objects.create(name="Only in org 2")
        jobs.enqueue("tests.record_org")
    with tenant(org1):
        jobs.enqueue("tests.record_org")
    assert SEEN == [("org2-homes", 1), ("savannah-test", 0)]
    assert Job.objects.filter(status=Job.Status.DONE, organization=org2).count() == 1


@pytest.mark.django_db
def test_cron_backend_queues_and_runner_executes(org1, settings):
    settings.JOBS_BACKEND = "cron"
    with tenant(org1):
        job = jobs.enqueue("tests.record_org")
    assert job.status == Job.Status.QUEUED and SEEN == []
    result = run_pending(time_limit=10)
    assert result["run"] >= 1 and ("savannah-test", 0) in SEEN


@pytest.mark.django_db
def test_failed_job_retries_with_backoff(settings):
    settings.JOBS_BACKEND = "cron"
    job = jobs.enqueue("tests.fail")
    run_pending(time_limit=10)
    job.refresh_from_db()
    assert job.status == Job.Status.QUEUED and job.attempts == 1 and "boom" in job.last_error
    assert job.run_at > timezone.now()


@pytest.mark.django_db
def test_per_org_schedule_runs_once_per_running_org_in_its_time_zone(org1, org2):
    jobs.daily(at="06:00", name="tests.nightly", per_org=True)(record_org)
    org2.timezone = "Europe/London"
    org2.save()
    # 06:30 in Nairobi = 03:30 in London: due for org1 only.
    now = datetime(2026, 10, 12, 6, 30, tzinfo=ZoneInfo("Africa/Nairobi"))
    queued = [q for q in enqueue_due_schedules(now) if q.startswith("tests.nightly")]
    assert queued == ["tests.nightly@savannah-test"]
    assert enqueue_due_schedules(now) == [q for q in enqueue_due_schedules(now) if not q.startswith("tests.nightly")]
    later = now + timedelta(hours=4)
    assert "tests.nightly@org2-homes" in enqueue_due_schedules(later)
    assert ScheduleState.objects.filter(name="tests.nightly").count() == 2


@pytest.mark.django_db
def test_suspended_orgs_get_no_scheduled_jobs(org1, org2):
    jobs.daily(at="06:00", name="tests.nightly", per_org=True)(record_org)
    org2.status = "suspended"
    org2.save()
    now = datetime(2026, 10, 12, 9, 0, tzinfo=ZoneInfo("Africa/Nairobi"))
    queued = [q for q in enqueue_due_schedules(now) if q.startswith("tests.nightly")]
    assert queued == ["tests.nightly@savannah-test"]


@pytest.mark.django_db
def test_lock_prevents_overlapping_runs():
    token = acquire_lock(60)
    assert token and acquire_lock(60) is None
    assert run_pending(time_limit=5)["locked"] is True
    release_lock(token)
    assert run_pending(time_limit=5)["locked"] is False
