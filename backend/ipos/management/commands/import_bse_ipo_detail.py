"""Founder-triggered offline BSE DisplayIPO normalization while feed access is disabled."""

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ipos.detail_enrichment import BSEIPOIssueDetailProvider, record_detail_observation


class Command(BaseCommand):
    help = "Import a saved permitted BSE issue-detail HTML or JSON response"

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--file", required=True)
        parser.add_argument("--source-url", required=True)

    def handle(self, *args, **options):
        source = Path(options["file"]).resolve()
        url = options["source_url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in {
            "www.bseindia.com",
            "api.bseindia.com",
        }:
            raise CommandError("An official BSE HTTPS source URL is required")
        if source.is_relative_to(Path.cwd()):
            raise CommandError("Saved BSE source must be outside Git")
        try:
            if source.stat().st_size > 2_000_000:
                raise CommandError("Saved BSE detail exceeds 2 MB")
            body = source.read_text(encoding="utf-8")
            raw = json.loads(body) if source.suffix.lower() == ".json" else body
            normalized = BSEIPOIssueDetailProvider().normalize(raw, symbol=options["symbol"])
            observation = record_detail_observation(
                source_key="bse",
                symbol=options["symbol"],
                source_url=url,
                raw=raw,
                normalized=normalized,
                fetched_at=datetime.fromtimestamp(source.stat().st_mtime, tz=UTC),
            )
        except (OSError, UnicodeError, ValueError, ValidationError) as exc:
            raise CommandError("Saved BSE issue detail failed validation") from exc
        self.stdout.write(self.style.SUCCESS(f"Saved BSE detail for {observation.symbol}"))
