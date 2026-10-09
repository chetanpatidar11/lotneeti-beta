from django.core.management.base import BaseCommand

from ipos.tasks import run_ipo_sync


class Command(BaseCommand):
    help = "Run the same coordinated IPO pipeline used by Founder Admin and Celery"

    def add_arguments(self, parser):
        parser.add_argument("--provider", choices=("investorgain",))

    def handle(self, *args, **options):
        provider = options["provider"]
        outcomes = run_ipo_sync(provider=provider or "all")
        for key, result in outcomes.items():
            self.stdout.write(
                f"{key.upper()}: {result['status']}"
                + (
                    f" — {result.get('fetched', result.get('discovered', 0))} fetched/discovered"
                    if result["status"] == "OK"
                    else f" — {result.get('reason', result.get('error', ''))}"
                )
            )
