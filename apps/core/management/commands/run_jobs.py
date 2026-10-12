"""Process due schedules and queued jobs. Run from cron every five minutes:

    */5 * * * * /home/USER/virtualenv/APP/3.12/bin/python /home/USER/APP/manage.py run_jobs >> /home/USER/APP/logs/cron.log 2>&1
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.jobs.runner import run_pending


class Command(BaseCommand):
    help = "Run due scheduled tasks and queued background jobs (database lock, retries, time limit)."

    def add_arguments(self, parser):
        parser.add_argument("--time-limit", type=int, default=settings.JOBS_RUN_TIME_LIMIT, help="Seconds before stopping.")

    def handle(self, *args, **options):
        result = run_pending(time_limit=options["time_limit"])
        if result["locked"]:
            self.stdout.write("Another run_jobs process is running; nothing to do.")
            return
        self.stdout.write(self.style.SUCCESS(
            f"Scheduled: {len(result['scheduled'])} · Jobs run: {result['run']} · Failed: {result['failed']}"
        ))
