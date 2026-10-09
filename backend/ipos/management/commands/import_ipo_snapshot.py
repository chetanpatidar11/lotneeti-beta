"""Stage one normalized, permissioned IPO record for Founder review."""

import json
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from ipos.feed_ingest import NormalizedExchangeIPOProvider, record_exchange_snapshot
from ipos.models import IPO


class Command(BaseCommand):
    help = "Stage an approved NSE/BSE/SEBI normalized IPO JSON file; never fetches a website"

    def add_arguments(self, parser):
        parser.add_argument("--ipo-id", required=True)
        parser.add_argument("--source", required=True, choices=("nse", "bse", "sebi"))
        parser.add_argument("--record-id", required=True)
        parser.add_argument("--observed-at", required=True)
        parser.add_argument("--file", required=True)

    def handle(self, *args, **options):
        source_file = Path(options["file"])
        try:
            if source_file.stat().st_size > 1_000_000:
                raise CommandError("IPO source file exceeds the 1 MB limit")
            raw = json.loads(source_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise CommandError("IPO source file must contain one JSON object")
            observed_at = datetime.fromisoformat(options["observed_at"])
            ipo = IPO.objects.get(pk=options["ipo_id"])
            record = NormalizedExchangeIPOProvider(options["source"]).normalize(
                raw,
                source_record_id=options["record_id"],
                observed_at=observed_at,
            )
            snapshot = record_exchange_snapshot(ipo=ipo, record=record)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CommandError("Could not read a valid UTF-8 JSON source file") from exc
        except IPO.DoesNotExist as exc:
            raise CommandError("Canonical IPO was not found") from exc
        except (ValueError, TypeError, KeyError, ValidationError) as exc:
            raise CommandError("IPO source record failed normalization or validation") from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Staged {snapshot.link.source_key}:{snapshot.link.source_record_id} "
                f"for review (snapshot {snapshot.pk}); canonical IPO unchanged"
            )
        )
