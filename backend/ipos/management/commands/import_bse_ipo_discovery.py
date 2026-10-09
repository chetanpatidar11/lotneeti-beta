"""Import a saved, permissioned BSE issue list without website automation."""

import json
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ipos.bse_feed import record_bse_discovery_rows


class Command(BaseCommand):
    help = "Import a saved official BSE discovery JSON list"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True)
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--observed-at", required=True)

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()
        if path.is_relative_to(Path.cwd()):
            raise CommandError("Saved BSE source file must be outside Git")
        try:
            rows = json.loads(path.read_text())
            observed_at = datetime.fromisoformat(options["observed_at"])
            created, total = record_bse_discovery_rows(
                rows, source_url=options["source_url"], observed_at=observed_at
            )
        except (OSError, ValueError, ValidationError) as exc:
            raise CommandError("BSE saved discovery could not be imported") from exc
        self.stdout.write(f"BSE discovery: {total} rows, {created} new observations")
