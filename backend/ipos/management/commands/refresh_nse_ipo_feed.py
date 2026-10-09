"""Offline import of an already obtained, permissioned NSE response."""

import json
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ipos.feed_watch import record_nse_current_rows

MAX_BYTES = 1_000_000


class Command(BaseCommand):
    help = "Import an approved saved NSE response; no website request is made"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Saved response obtained with permission")
        parser.add_argument("--observed-at", required=True, help="ISO timestamp with timezone")

    def handle(self, *args, **options):
        try:
            source = Path(options["file"])
            if source.stat().st_size > MAX_BYTES:
                raise CommandError("NSE response exceeds the 1 MB limit")
            body = source.read_bytes()
            observed_at = datetime.fromisoformat(options["observed_at"])
            if len(body) > MAX_BYTES:
                raise CommandError("NSE response exceeds the 1 MB limit")
            rows = json.loads(body)
            created, total = record_nse_current_rows(rows, observed_at=observed_at)
        except OSError as exc:
            raise CommandError(
                "NSE fetch/import failed; saved observations were preserved"
            ) from exc
        except (ValueError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise CommandError(
                "NSE response failed validation; saved observations were preserved"
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Saved {created} new NSE observations from {total} issues")
        )
