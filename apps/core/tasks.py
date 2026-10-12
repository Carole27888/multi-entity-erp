"""Platform housekeeping jobs."""

from datetime import timedelta

from django.utils import timezone

from .jobs import daily


@daily(at="03:30")
def purge_finished_jobs():
    """Finished jobs older than 30 days and heartbeats older than 14 days are removed."""
    from .models import Job, JobRunnerHeartbeat

    now = timezone.now()
    Job.objects.filter(status=Job.Status.DONE, finished_at__lt=now - timedelta(days=30)).delete()
    JobRunnerHeartbeat.objects.filter(started_at__lt=now - timedelta(days=14)).delete()
