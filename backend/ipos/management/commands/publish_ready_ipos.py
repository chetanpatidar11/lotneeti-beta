"""Founder-triggered publication of complete official facts in local preview only."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from ipos.bse_feed import current_bse_issues
from ipos.feed_watch import current_feed_issues
from ipos.local_publication import publish_local_enriched_issue


class Command(BaseCommand):
    help = "Publish READY enriched IPOs to the isolated local test database"

    def add_arguments(self, parser):
        parser.add_argument("--rights-reference", required=True)

    def handle(self, *args, **options):
        nse = current_feed_issues()
        nse_symbols = {issue["symbol"] for issue in nse}
        bse_only = [item for item in current_bse_issues() if item["symbol"] not in nse_symbols]
        for issue in nse + bse_only:
            if issue["enrichment_state"] != "READY":
                self.stdout.write(f"{issue['symbol']}: {issue['enrichment_state']}")
                continue
            try:
                _, changed = publish_local_enriched_issue(
                    issue, rights_reference=options["rights_reference"]
                )
            except (ValidationError, ValueError):
                self.stdout.write(f"{issue['symbol']}: publication needs Founder review")
                continue
            self.stdout.write(f"{issue['symbol']}: {'published' if changed else 'unchanged'}")
